from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SkillCategory = Literal[
    "language",
    "backend",
    "ai",
    "data",
    "devops",
    "workflow",
    "soft_skill",
    "other",
]


class SkillRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: SkillCategory = "other"
    evidence: str | None = None
    required: bool = True

    @field_validator("name")
    @classmethod
    def require_non_blank_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("skill name cannot be blank")
        return cleaned


class StructuredJD(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_job_id: str
    job_title: str
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    skills: list[SkillRequirement] = Field(default_factory=list)
    risk_points: list[str] = Field(default_factory=list)
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("responsibilities", "requirements", "risk_points")
    @classmethod
    def dedupe_text_items(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
        return result

    @field_validator("skills")
    @classmethod
    def dedupe_skills(cls, value: list[SkillRequirement]) -> list[SkillRequirement]:
        seen: set[str] = set()
        result: list[SkillRequirement] = []
        for skill in value:
            key = skill.name.lower()
            if key not in seen:
                seen.add(key)
                result.append(skill)
        return result
