from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.jd import SkillCategory


class SkillFrequency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: SkillCategory
    count: int = Field(ge=0)
    job_count: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)
    example_job_ids: list[str] = Field(default_factory=list)


class SkillCategorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: SkillCategory
    skill_count: int = Field(ge=0)
    mention_count: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)


class SkillPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills: tuple[str, str]
    count: int = Field(ge=0)
    example_job_ids: list[str] = Field(default_factory=list)

    @field_validator("skills")
    @classmethod
    def sort_pair(cls, value: tuple[str, str]) -> tuple[str, str]:
        first, second = sorted((value[0].strip(), value[1].strip()), key=str.lower)
        if not first or not second or first.lower() == second.lower():
            raise ValueError("skill pair must contain two distinct skills")
        return (first, second)


class SkillAnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_jobs: int = Field(ge=0)
    top_skills: list[SkillFrequency] = Field(default_factory=list)
    category_distribution: list[SkillCategorySummary] = Field(default_factory=list)
    common_skill_pairs: list[SkillPair] = Field(default_factory=list)
    required_skill_names: list[str] = Field(default_factory=list)
    summary: str
    recommendations: list[str] = Field(default_factory=list)
