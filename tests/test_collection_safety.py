from pathlib import Path

import pytest

from app.schemas.collect import CollectionRequest
from app.services.collection_safety import (
    CollectionSafetyPolicy,
    assert_safe_collection_request,
    looks_like_main_browser_profile,
    validate_collection_request,
)


def test_default_low_frequency_request_is_allowed() -> None:
    request = CollectionRequest(keyword="AI Agent", city="上海", pages=2)

    result = validate_collection_request(request)

    assert result.allowed is True
    assert result.reasons == ()
    assert ".boss-zhipin-scraper" in result.effective_profile_dir


def test_pages_above_policy_limit_are_rejected() -> None:
    request = CollectionRequest(keyword="AI Agent", pages=4)

    result = validate_collection_request(request)

    assert result.allowed is False
    assert "pages=4 exceeds low-frequency limit" in result.reasons[0]


def test_copy_login_state_is_rejected_by_default() -> None:
    request = CollectionRequest(keyword="AI Agent", copy_login_state=True)

    result = validate_collection_request(request)

    assert result.allowed is False
    assert result.reasons == (
        "copy_login_state is disabled; login inside the dedicated Chrome profile",
    )


def test_main_browser_profile_is_rejected() -> None:
    request = CollectionRequest(
        keyword="AI Agent",
        profile_dir="C:/Users/demo/AppData/Local/Google/Chrome/User Data",
    )

    result = validate_collection_request(request)

    assert result.allowed is False
    assert "main browser profile" in result.reasons[0]


def test_custom_non_main_profile_is_allowed_with_warning() -> None:
    request = CollectionRequest(
        keyword="AI Agent",
        profile_dir="D:/job-agent/chrome-profile",
    )

    result = validate_collection_request(request)

    assert result.allowed is True
    assert result.warnings == (
        "profile_dir is not the default dedicated profile; verify it is isolated before use",
    )


def test_auto_apply_and_auto_message_are_rejected() -> None:
    request = CollectionRequest(
        keyword="AI Agent",
        auto_apply=True,
        auto_message=True,
    )

    result = validate_collection_request(request)

    assert result.allowed is False
    assert result.reasons == (
        "auto_apply is out of scope for this project",
        "auto_message is out of scope for this project",
    )


def test_assert_safe_collection_request_raises_on_unsafe_request() -> None:
    request = CollectionRequest(keyword="AI Agent", pages=5)

    with pytest.raises(ValueError, match="low-frequency limit"):
        assert_safe_collection_request(request)


def test_policy_can_override_default_profile_and_page_limit() -> None:
    policy = CollectionSafetyPolicy(
        max_pages_per_run=1,
        dedicated_profile_dir=Path("D:/safe/boss-profile"),
    )
    request = CollectionRequest(keyword="AI Agent", pages=1)

    result = validate_collection_request(request, policy)

    assert result.allowed is True
    assert result.effective_profile_dir == str(Path("D:/safe/boss-profile"))


def test_main_profile_detector_handles_common_profile_paths() -> None:
    assert looks_like_main_browser_profile(
        "C:/Users/demo/AppData/Local/Google/Chrome/User Data/Default"
    )
    assert looks_like_main_browser_profile("/Users/demo/Library/Application Support/Google/Chrome")
