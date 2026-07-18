from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class JobOverviewRow(BaseModel):
    """One row in the recommendation overview table / CSV export."""

    model_config = ConfigDict(extra="forbid")

    rank: int
    company: str
    job_title: str
    location: str
    salary: str
    experience: str
    education: str
    company_scale: str
    company_stage: str
    company_industry: str
    match_score: int
    recommendation_level: str
    job_url: str


class FinalReport(BaseModel):
    """The final workflow deliverable: structured overview plus rendered Markdown."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    total_jobs: int
    matched_jobs: int
    priority_jobs: int
    overview: list[JobOverviewRow] = Field(default_factory=list)
    markdown: str
