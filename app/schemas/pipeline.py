from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class PipelineArtifacts(BaseModel):
    """Files produced by one offline pipeline run."""

    model_config = ConfigDict(extra="forbid")

    structured_jds_path: Path | None = None
    skill_report_path: Path | None = None
    markdown_report_path: Path | None = None


class PipelineResult(BaseModel):
    """High-level execution summary for the job analysis pipeline."""

    model_config = ConfigDict(extra="forbid")

    raw_job_count: int = Field(ge=0)
    normalized_job_count: int = Field(ge=0)
    saved_job_count: int = Field(ge=0)
    structured_jd_count: int = Field(ge=0)
    top_skill_names: list[str] = Field(default_factory=list)
    database_url: str | None = None
    artifacts: PipelineArtifacts = Field(default_factory=PipelineArtifacts)
