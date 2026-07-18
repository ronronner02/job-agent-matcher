from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from app.schemas.collect import CollectionRequest


MAIN_BROWSER_PROFILE_MARKERS = (
    "appdata/local/google/chrome/user data",
    "library/application support/google/chrome",
    ".config/google-chrome",
    ".config/chromium",
    "microsoft/edge/user data",
)


@dataclass(frozen=True)
class CollectionSafetyPolicy:
    """Safety limits applied before a real collector can run."""

    max_pages_per_run: int = 3
    min_seconds_between_runs: int = 600
    dedicated_profile_dir: Path = field(
        default_factory=lambda: Path.home() / ".boss-zhipin-scraper" / "chrome-profile"
    )
    allow_copy_login_state: bool = False
    allow_auto_apply: bool = False
    allow_auto_message: bool = False


@dataclass(frozen=True)
class SafetyCheckResult:
    allowed: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    effective_profile_dir: str


def validate_collection_request(
    request: CollectionRequest,
    policy: CollectionSafetyPolicy | None = None,
) -> SafetyCheckResult:
    policy = policy or CollectionSafetyPolicy()
    reasons: list[str] = []
    warnings: list[str] = []

    if request.pages > policy.max_pages_per_run:
        reasons.append(
            f"pages={request.pages} exceeds low-frequency limit "
            f"max_pages_per_run={policy.max_pages_per_run}"
        )

    if request.copy_login_state and not policy.allow_copy_login_state:
        reasons.append("copy_login_state is disabled; login inside the dedicated Chrome profile")

    if request.use_main_browser_profile:
        reasons.append("main browser profile reuse is disabled")

    if request.auto_apply and not policy.allow_auto_apply:
        reasons.append("auto_apply is out of scope for this project")

    if request.auto_message and not policy.allow_auto_message:
        reasons.append("auto_message is out of scope for this project")

    profile_dir = effective_profile_dir(request, policy)
    if looks_like_main_browser_profile(profile_dir):
        reasons.append(f"profile_dir appears to be a main browser profile: {profile_dir}")
    elif profile_dir != policy.dedicated_profile_dir.expanduser():
        warnings.append(
            "profile_dir is not the default dedicated profile; verify it is isolated before use"
        )

    return SafetyCheckResult(
        allowed=not reasons,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        effective_profile_dir=str(profile_dir),
    )


def assert_safe_collection_request(
    request: CollectionRequest,
    policy: CollectionSafetyPolicy | None = None,
) -> CollectionRequest:
    result = validate_collection_request(request, policy)
    if not result.allowed:
        raise ValueError("; ".join(result.reasons))
    return request


def effective_profile_dir(
    request: CollectionRequest,
    policy: CollectionSafetyPolicy,
) -> Path:
    if request.profile_dir:
        return Path(request.profile_dir).expanduser()
    return policy.dedicated_profile_dir.expanduser()


def looks_like_main_browser_profile(profile_dir: str | Path) -> bool:
    normalized = str(Path(profile_dir).expanduser()).replace("\\", "/").lower()
    return any(marker in normalized for marker in MAIN_BROWSER_PROFILE_MARKERS)


def policy_from_env(env: Mapping[str, str] | None = None) -> CollectionSafetyPolicy:
    values = env or os.environ
    return CollectionSafetyPolicy(
        max_pages_per_run=_int_env(values, "BOSS_MAX_PAGES_PER_RUN", 3),
        min_seconds_between_runs=_int_env(values, "BOSS_MIN_SECONDS_BETWEEN_RUNS", 600),
        dedicated_profile_dir=Path(
            values.get(
                "BOSS_DEDICATED_PROFILE_DIR",
                str(Path.home() / ".boss-zhipin-scraper" / "chrome-profile"),
            )
        ).expanduser(),
        allow_copy_login_state=_bool_env(values, "BOSS_ALLOW_COPY_LOGIN_STATE", False),
    )


def _int_env(values: Mapping[str, str], key: str, default: int) -> int:
    raw = values.get(key)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _bool_env(values: Mapping[str, str], key: str, default: bool) -> bool:
    raw = values.get(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
