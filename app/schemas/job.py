from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Platform = Literal["boss_zhipin"]

SalaryUnit = Literal["month", "day", "hour", "year"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RawJobPost(BaseModel):
    """Raw job data after the external collector output enters our system."""

    model_config = ConfigDict(extra="forbid")

    platform: Platform = "boss_zhipin"
    keyword: str | None = None
    city: str | None = None
    source_job_id: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    address: str | None = None
    salary: str | None = None
    tags: str | None = None
    skills: list[str] = Field(default_factory=list)
    job_url: str | None = None
    detail_url: str | None = None
    jd_text: str | None = None
    # Company / employer metadata promoted out of raw_payload.
    company_scale: str | None = None
    company_stage: str | None = None
    company_industry: str | None = None
    company_link: str | None = None
    boss_name: str | None = None
    boss_title: str | None = None
    welfare: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    collected_at: datetime = Field(default_factory=utc_now)

    @field_validator("skills", mode="before")
    @classmethod
    def normalize_skill_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split("|") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]


class NormalizedJobPost(BaseModel):
    """Stable internal job representation used by downstream services."""

    model_config = ConfigDict(extra="forbid")

    platform: Platform
    source_job_id: str
    keyword: str
    city: str
    job_title: str
    company: str
    location: str
    address: str | None = None
    salary: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_unit: SalaryUnit | None = None
    experience_required: str | None = None
    education_required: str | None = None
    jd_text: str | None = None
    job_url: str | None = None
    detail_url: str | None = None
    # Company / employer metadata, first-class so reports and prompts never
    # have to dig through raw_payload.
    company_scale: str | None = None
    company_stage: str | None = None
    company_industry: str | None = None
    company_link: str | None = None
    boss_name: str | None = None
    boss_title: str | None = None
    welfare: list[str] = Field(default_factory=list)
    skill_keywords: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator(
        "source_job_id",
        "keyword",
        "city",
        "job_title",
        "company",
        "location",
    )
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field cannot be blank")
        return cleaned

    @field_validator("skill_keywords")
    @classmethod
    def dedupe_skills(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for skill in value:
            cleaned = skill.strip()
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result

    @field_validator("welfare")
    @classmethod
    def dedupe_welfare(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
        return result
