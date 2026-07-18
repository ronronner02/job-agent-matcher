from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations

from app.schemas.jd import SkillCategory, StructuredJD
from app.schemas.skill import (
    SkillAnalysisReport,
    SkillCategorySummary,
    SkillFrequency,
    SkillPair,
)


def analyze_skills(
    structured_jds: list[StructuredJD],
    *,
    top_n: int = 10,
    pair_top_n: int = 10,
) -> SkillAnalysisReport:
    total_jobs = len(structured_jds)
    skill_mentions: Counter[str] = Counter()
    skill_job_counts: Counter[str] = Counter()
    skill_categories: dict[str, SkillCategory] = {}
    skill_examples: dict[str, list[str]] = defaultdict(list)
    category_mentions: Counter[SkillCategory] = Counter()
    category_jobs: dict[SkillCategory, set[str]] = defaultdict(set)
    pair_counts: Counter[tuple[str, str]] = Counter()
    pair_examples: dict[tuple[str, str], list[str]] = defaultdict(list)

    for jd in structured_jds:
        unique_skills: dict[str, tuple[str, SkillCategory]] = {}
        for skill in jd.skills:
            key = skill.name.lower()
            skill_mentions[key] += 1
            skill_categories[key] = skill.category
            unique_skills[key] = (skill.name, skill.category)
            if jd.source_job_id not in skill_examples[key]:
                skill_examples[key].append(jd.source_job_id)
            category_mentions[skill.category] += 1
            category_jobs[skill.category].add(jd.source_job_id)

        for key in unique_skills:
            skill_job_counts[key] += 1

        names = sorted((name for name, _ in unique_skills.values()), key=str.lower)
        for first, second in combinations(names, 2):
            pair = tuple(sorted((first, second), key=str.lower))
            pair_counts[pair] += 1
            if jd.source_job_id not in pair_examples[pair]:
                pair_examples[pair].append(jd.source_job_id)

    top_skills = [
        SkillFrequency(
            name=_display_name(skill_key, structured_jds),
            category=skill_categories[skill_key],
            count=count,
            job_count=skill_job_counts[skill_key],
            coverage=_coverage(skill_job_counts[skill_key], total_jobs),
            example_job_ids=skill_examples[skill_key][:3],
        )
        for skill_key, count in sorted(
            skill_mentions.items(),
            key=lambda item: (-skill_job_counts[item[0]], -item[1], item[0]),
        )[:top_n]
    ]

    category_distribution = [
        SkillCategorySummary(
            category=category,
            skill_count=len({
                key for key, skill_category in skill_categories.items() if skill_category == category
            }),
            mention_count=category_mentions[category],
            coverage=_coverage(len(category_jobs[category]), total_jobs),
        )
        for category in sorted(category_mentions, key=lambda item: (-len(category_jobs[item]), item))
    ]

    common_skill_pairs = [
        SkillPair(
            skills=pair,
            count=count,
            example_job_ids=pair_examples[pair][:3],
        )
        for pair, count in sorted(pair_counts.items(), key=lambda item: (-item[1], item[0]))[:pair_top_n]
    ]

    required_skill_names = [skill.name for skill in top_skills]
    return SkillAnalysisReport(
        total_jobs=total_jobs,
        top_skills=top_skills,
        category_distribution=category_distribution,
        common_skill_pairs=common_skill_pairs,
        required_skill_names=required_skill_names,
        summary=build_skill_summary(total_jobs, top_skills, category_distribution),
        recommendations=build_recommendations(top_skills, category_distribution),
    )


def build_skill_summary(
    total_jobs: int,
    top_skills: list[SkillFrequency],
    categories: list[SkillCategorySummary],
) -> str:
    if total_jobs == 0:
        return "暂无岗位数据，无法生成技能画像。"
    top_skill_text = "、".join(skill.name for skill in top_skills[:5]) or "暂无明确技能"
    top_category = categories[0].category if categories else "other"
    return f"共分析 {total_jobs} 个岗位，高频技能包括 {top_skill_text}，技能需求主要集中在 {top_category} 类别。"


def build_recommendations(
    top_skills: list[SkillFrequency],
    categories: list[SkillCategorySummary],
) -> list[str]:
    recommendations: list[str] = []
    if top_skills:
        recommendations.append(
            f"优先准备 {top_skills[0].name}，它覆盖了 {top_skills[0].coverage:.0%} 的样本岗位。"
        )
    if any(category.category == "ai" for category in categories):
        recommendations.append("准备 RAG/Agent/LLM 应用链路的项目讲解，重点说明检索、工具调用和评估方式。")
    if any(category.category == "backend" for category in categories):
        recommendations.append("补齐后端接口、性能优化和服务部署案例，便于支撑工程落地能力。")
    if any(category.category == "data" for category in categories):
        recommendations.append("整理数据清洗、向量数据库和 SQL 查询经验，便于匹配数据相关 JD 要求。")
    return recommendations


def _coverage(job_count: int, total_jobs: int) -> float:
    if total_jobs == 0:
        return 0.0
    return round(job_count / total_jobs, 4)


def _display_name(skill_key: str, structured_jds: list[StructuredJD]) -> str:
    for jd in structured_jds:
        for skill in jd.skills:
            if skill.name.lower() == skill_key:
                return skill.name
    return skill_key
