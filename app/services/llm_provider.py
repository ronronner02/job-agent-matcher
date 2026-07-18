from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from typing import Any


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    """Small OpenAI-compatible chat-completions client using only stdlib."""

    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout_seconds: int = 60
    max_tokens: int | None = None
    retry_count: int = 2
    retry_backoff_seconds: float = 2.0

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "OpenAICompatibleProvider":
        values = _load_provider_config(env_file)
        api_key = _config_value(values, "AI_MATCHER_API_KEY", "OPENAI_API_KEY")
        if not api_key:
            raise ValueError("set AI_MATCHER_API_KEY or OPENAI_API_KEY before using the real AI provider")

        base_url = _config_value(values, "AI_MATCHER_BASE_URL", "OPENAI_BASE_URL")
        model = _config_value(values, "AI_MATCHER_MODEL", "OPENAI_MODEL")
        return cls(
            api_key=api_key,
            base_url=base_url or cls.base_url,
            model=model or cls.model,
            timeout_seconds=_positive_int_config(values, "AI_MATCHER_TIMEOUT_SECONDS", cls.timeout_seconds),
            max_tokens=_optional_positive_int_config(values, "AI_MATCHER_MAX_TOKENS"),
            retry_count=_non_negative_int_config(values, "AI_MATCHER_RETRY_COUNT", cls.retry_count),
            retry_backoff_seconds=_positive_float_config(
                values,
                "AI_MATCHER_RETRY_BACKOFF_SECONDS",
                cls.retry_backoff_seconds,
            ),
        )

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": "你是严谨的招聘数据分析助手，只能基于用户提供的信息分析。",
                },
                {"role": "user", "content": prompt},
            ],
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.base_url.rstrip('/')}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        body = self._post_with_retries(request)

        return _extract_chat_content(json.loads(body))

    def _post_with_retries(self, request: urllib.request.Request) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                if exc.code < 500:
                    detail = exc.read().decode("utf-8", errors="replace")[-1000:]
                    raise RuntimeError(f"AI provider HTTP {exc.code}: {detail}") from exc
                last_error = exc
            except (TimeoutError, urllib.error.URLError, OSError) as exc:
                last_error = exc

            if attempt < self.retry_count:
                time.sleep(self.retry_backoff_seconds * (attempt + 1))

        assert last_error is not None
        if isinstance(last_error, TimeoutError):
            raise RuntimeError(
                f"AI provider timed out after {self.timeout_seconds} seconds; "
                "increase AI_MATCHER_TIMEOUT_SECONDS or reduce --max-jobs/--batch-size"
            ) from last_error
        if isinstance(last_error, urllib.error.HTTPError):
            detail = last_error.read().decode("utf-8", errors="replace")[-1000:]
            raise RuntimeError(f"AI provider HTTP {last_error.code}: {detail}") from last_error
        if isinstance(last_error, urllib.error.URLError):
            raise RuntimeError(f"AI provider request failed: {last_error.reason}") from last_error
        raise RuntimeError(f"AI provider connection failed: {last_error}") from last_error


def _extract_chat_content(payload: dict[str, Any]) -> str:
    """Pull the text out of an OpenAI-compatible chat response, tolerantly.

    Endpoints vary: standard OpenAI uses ``choices[0].message.content``; some
    reasoning models leave that empty and put text in ``reasoning_content``;
    completion-style servers use ``choices[0].text``. Errors arrive as a
    top-level ``error`` object. On any failure we include a truncated dump of
    the actual payload so the real problem is visible instead of hidden.
    """

    if not isinstance(payload, dict):
        raise RuntimeError(f"AI provider response is not a JSON object: {_short_dump(payload)}")

    # Explicit provider error object (rate limit, bad key, content filter, ...).
    error = payload.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(f"AI provider returned an error: {message or _short_dump(error)}")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(
            f"AI provider response has no choices[0].message.content: {_short_dump(payload)}"
        )

    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}

    # Preferred: message.content. Fall back to reasoning_content, then text.
    for candidate in (message.get("content"), message.get("reasoning_content"), first.get("text")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate

    finish_reason = first.get("finish_reason")
    if finish_reason == "length":
        raise RuntimeError(
            "AI provider returned empty content (finish_reason=length); "
            "raise AI_MATCHER_MAX_TOKENS or lower --batch-size"
        )
    raise RuntimeError(
        "AI provider response has empty choices[0].message.content: "
        f"{_short_dump(payload)}"
    )


def _short_dump(payload: Any, limit: int = 800) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(payload)
    return text[:limit]


def _load_provider_config(env_file: str | Path | None = None) -> dict[str, str]:
    values = _read_dotenv(Path(env_file)) if env_file else _read_default_dotenv()
    values.update({key: value for key, value in os.environ.items() if value is not None})
    return values


def _read_default_dotenv() -> dict[str, str]:
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]
    for path in candidates:
        if path.exists():
            return _read_dotenv(path)
    return {}


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#") or "=" not in cleaned:
            continue
        key, value = cleaned.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _config_value(values: Mapping[str, str], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if value and value.strip():
            return value.strip()
    return None


def _positive_int_config(values: Mapping[str, str], key: str, default: int) -> int:
    raw = values.get(key)
    if raw is None or not raw.strip():
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{key} must be positive")
    return value


def _non_negative_int_config(values: Mapping[str, str], key: str, default: int) -> int:
    raw = values.get(key)
    if raw is None or not raw.strip():
        return default
    value = int(raw)
    if value < 0:
        raise ValueError(f"{key} must be non-negative")
    return value


def _positive_float_config(values: Mapping[str, str], key: str, default: float) -> float:
    raw = values.get(key)
    if raw is None or not raw.strip():
        return default
    value = float(raw)
    if value <= 0:
        raise ValueError(f"{key} must be positive")
    return value


def _optional_positive_int_config(values: Mapping[str, str], key: str) -> int | None:
    raw = values.get(key)
    if raw is None or not raw.strip() or raw.strip() == "0":
        return None
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{key} must be positive or 0 to disable")
    return value
