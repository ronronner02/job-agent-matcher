from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FullJobAgentRequest(BaseModel):
    """One end-to-end job-agent run: collect -> match -> report."""

    model_config = ConfigDict(extra="forbid")

    resume_file: str
    keyword: str
    cities: list[str] = Field(default_factory=lambda: ["上海"])
    pages: int = Field(default=1, ge=1)
    cdp_port: int = Field(default=9222, ge=1024, le=65535)
    scraper_root: str | None = None
    output_dir: str = "data/reports"
    max_jobs: int = Field(default=30, ge=1)
    include_detail: bool = True
    max_details: int | None = Field(default=None, ge=1)
    batch_size: int = Field(default=0, ge=0)
    persist: bool = True
    database_url: str | None = None
    # BOSS fuzzy-matches the search keyword, so a query like "AI Agent实习生"
    # also returns unrelated 实习生 postings. When set, only jobs whose title
    # contains at least one of these substrings are kept. Empty = keep all.
    title_filters: list[str] = Field(default_factory=list)

    @field_validator("title_filters")
    @classmethod
    def clean_title_filters(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @field_validator("keyword", "resume_file")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field cannot be blank")
        return cleaned

    @field_validator("cities")
    @classmethod
    def require_cities(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for city in value:
            item = city.strip()
            if item and item not in seen:
                seen.add(item)
                cleaned.append(item)
        if not cleaned:
            raise ValueError("cities must contain at least one city")
        return cleaned


class WorkflowArtifacts(BaseModel):
    """Filesystem paths for everything a run produces."""

    model_config = ConfigDict(extra="forbid")

    job_overview_csv: str | None = None
    structured_jobs_json: str | None = None
    skill_analysis_json: str | None = None
    match_results_json: str | None = None
    final_report_md: str | None = None
    steps_jsonl: str | None = None


class FullJobAgentResult(BaseModel):
    """Summary returned to the caller after a full run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    keyword: str
    cities: list[str] = Field(default_factory=list)
    raw_job_count: int = 0
    unique_job_count: int = 0
    saved_job_count: int = 0
    structured_jd_count: int = 0
    matched_job_count: int = 0
    priority_job_count: int = 0
    failed_step: str | None = None
    error_message: str | None = None
    artifacts: WorkflowArtifacts = Field(default_factory=WorkflowArtifacts)
