from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


RecommendationLevel = Literal["优先投递", "可以投递", "谨慎投递"]


class JobMatchResult(BaseModel):
    """One resume-vs-job match, structured so it can be sorted and stored."""

    model_config = ConfigDict(extra="ignore")

    source_job_id: str
    rank: int = Field(default=0, ge=0)
    match_score: int = Field(ge=0, le=100)
    recommendation_level: RecommendationLevel = "谨慎投递"
    matched_evidence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    resume_suggestions: list[str] = Field(default_factory=list)
    interview_focus: list[str] = Field(default_factory=list)

    @field_validator("source_job_id")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("source_job_id cannot be blank")
        return cleaned

    @field_validator(
        "matched_evidence",
        "gaps",
        "resume_suggestions",
        "interview_focus",
        mode="before",
    )
    @classmethod
    def coerce_string_lists(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            cleaned = value.strip()
            return [cleaned] if cleaned else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]


class JobMatchReport(BaseModel):
    """All structured match results for one workflow run, globally ranked."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    total_jobs: int = Field(ge=0)
    results: list[JobMatchResult] = Field(default_factory=list)
