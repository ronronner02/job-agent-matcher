from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Platform = Literal["boss_zhipin"]


class CollectionRequest(BaseModel):
    """User-facing collection request before it is allowed to run."""

    model_config = ConfigDict(extra="forbid")

    platform: Platform = "boss_zhipin"
    keyword: str
    city: str = "上海"
    pages: int = Field(default=1, ge=1)
    cdp_port: int = Field(default=9222, ge=1024, le=65535)
    profile_dir: str | None = None
    copy_login_state: bool = False
    use_main_browser_profile: bool = False
    auto_apply: bool = False
    auto_message: bool = False
    # Detail-page JD collection. Enabled by default so the JD text actually
    # reaches structuring and matching; can be disabled for a fast list-only run.
    include_detail: bool = True
    max_details: int | None = Field(default=None, ge=1)
    detail_output_path: str | None = None

    @field_validator("keyword", "city")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field cannot be blank")
        return cleaned
