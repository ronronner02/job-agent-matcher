from __future__ import annotations

import re

from app.schemas.jd import SkillCategory, SkillRequirement, StructuredJD
from app.schemas.job import NormalizedJobPost


SKILL_CATALOG: dict[str, SkillCategory] = {
    "Python": "language",
    "Java": "language",
    "SQL": "data",
    "FastAPI": "backend",
    "Spring": "backend",
    "RAG": "ai",
    "Agent": "ai",
    "AI Agent": "ai",
    "LLM": "ai",
    "大模型": "ai",
    "LangGraph": "ai",
    "MCP": "ai",
    "Prompt Engineering": "ai",
    "Prompt": "ai",
    "Embedding": "ai",
    "向量数据库": "data",
    "数据清洗": "data",
    "Docker": "devops",
    "知识库": "data",
    "检索": "data",
    "工具调用": "workflow",
    "接口": "backend",
    "性能优化": "backend",
}

RESPONSIBILITY_HINTS = ("负责", "参与", "建设", "开发", "封装", "优化", "维护", "设计")
REQUIREMENT_HINTS = ("要求", "熟悉", "掌握", "具备", "经验", "本科", "硕士", "优先")
RISK_HINTS = ("高并发", "性能优化", "从0到1", "落地", "跨团队", "复杂", "稳定性")


def structure_jd(job: NormalizedJobPost) -> StructuredJD:
    text = (job.jd_text or "").strip()
    sentences = split_sentences(text)
    responsibilities = [item for item in sentences if contains_any(item, RESPONSIBILITY_HINTS)]
    requirements = [item for item in sentences if contains_any(item, REQUIREMENT_HINTS)]

    if not responsibilities and text:
        responsibilities = sentences[:2]
    if job.experience_required:
        requirements.append(f"经验要求：{job.experience_required}")
    if job.education_required:
        requirements.append(f"学历要求：{job.education_required}")

    skills = extract_skills(job)
    risk_points = extract_risk_points(job, skills)
    summary = build_summary(job, skills, responsibilities)
    confidence = estimate_confidence(text, skills, responsibilities, requirements)

    return StructuredJD(
        source_job_id=job.source_job_id,
        job_title=job.job_title,
        responsibilities=responsibilities,
        requirements=requirements,
        skills=skills,
        risk_points=risk_points,
        summary=summary,
        confidence=confidence,
    )


def structure_jds(jobs: list[NormalizedJobPost]) -> list[StructuredJD]:
    return [structure_jd(job) for job in jobs]


def split_sentences(text: str) -> list[str]:
    if not text.strip():
        return []
    parts = re.split(r"[。；;\n]+", text)
    return [part.strip(" ，,\t") for part in parts if part.strip(" ，,\t")]


def extract_skills(job: NormalizedJobPost) -> list[SkillRequirement]:
    combined = " ".join(
        [
            job.job_title,
            job.jd_text or "",
            " ".join(job.skill_keywords),
            job.raw_payload.get("skills", "") if isinstance(job.raw_payload, dict) else "",
        ]
    )
    found: list[SkillRequirement] = []
    for skill, category in SKILL_CATALOG.items():
        if skill.lower() in combined.lower():
            found.append(
                SkillRequirement(
                    name=skill,
                    category=category,
                    evidence=find_evidence(combined, skill),
                    required=True,
                )
            )
    return found


def extract_risk_points(job: NormalizedJobPost, skills: list[SkillRequirement]) -> list[str]:
    text = " ".join([job.job_title, job.jd_text or "", job.experience_required or ""])
    risks: list[str] = []
    if contains_any(text, RISK_HINTS):
        risks.append("岗位可能强调落地复杂度、稳定性或性能结果，需要准备可量化项目案例。")
    if any(skill.name in {"RAG", "LLM", "Agent", "AI Agent", "LangGraph", "MCP"} for skill in skills):
        risks.append("岗位涉及大模型应用，需要能解释 RAG/Agent 链路、评估方式和工程取舍。")
    if job.experience_required and "经验不限" not in job.experience_required:
        risks.append(f"岗位标注 {job.experience_required}，需要用项目经验证明匹配度。")
    return risks


def build_summary(
    job: NormalizedJobPost,
    skills: list[SkillRequirement],
    responsibilities: list[str],
) -> str:
    skill_text = "、".join(skill.name for skill in skills[:6]) or "未识别到明确技能"
    if responsibilities:
        return f"{job.job_title} 主要围绕 {responsibilities[0]}，核心技能包括 {skill_text}。"
    return f"{job.job_title} 的核心技能包括 {skill_text}。"


def estimate_confidence(
    text: str,
    skills: list[SkillRequirement],
    responsibilities: list[str],
    requirements: list[str],
) -> float:
    score = 0.35
    if text:
        score += 0.2
    if skills:
        score += 0.2
    if responsibilities:
        score += 0.15
    if requirements:
        score += 0.1
    return min(score, 0.95)


def find_evidence(text: str, skill: str) -> str | None:
    index = text.lower().find(skill.lower())
    if index < 0:
        return None
    start = max(index - 20, 0)
    end = min(index + len(skill) + 20, len(text))
    return text[start:end].strip()


def contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)
