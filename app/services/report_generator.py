from __future__ import annotations

import csv
import io

from app.schemas.job import NormalizedJobPost
from app.schemas.match import JobMatchReport, JobMatchResult
from app.schemas.report import FinalReport, JobOverviewRow
from app.schemas.skill import SkillAnalysisReport


PRIORITY_LEVEL = "优先投递"


def build_final_report(
    match_report: JobMatchReport,
    jobs_by_id: dict[str, NormalizedJobPost],
    skill_report: SkillAnalysisReport | None = None,
) -> FinalReport:
    """Assemble the final deliverable from structured match results.

    The system owns ordering and formatting; the AI only supplied the per-job
    analysis inside ``match_report``. Rows for jobs missing metadata still render
    with '未提供' placeholders rather than being dropped.
    """

    ranked = sorted(match_report.results, key=lambda r: r.rank)
    overview = [_overview_row(result, jobs_by_id.get(result.source_job_id)) for result in ranked]
    priority = [r for r in ranked if r.recommendation_level == PRIORITY_LEVEL]

    markdown = _render_markdown(
        run_id=match_report.run_id,
        total_jobs=match_report.total_jobs,
        ranked=ranked,
        overview=overview,
        jobs_by_id=jobs_by_id,
        skill_report=skill_report,
        priority_count=len(priority),
    )

    return FinalReport(
        run_id=match_report.run_id,
        total_jobs=match_report.total_jobs,
        matched_jobs=len(ranked),
        priority_jobs=len(priority),
        overview=overview,
        markdown=markdown,
    )


def build_overview_csv(rows: list[JobOverviewRow]) -> str:
    """Render the overview rows as CSV text (UTF-8, Excel-friendly headers)."""

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "排名",
            "公司",
            "岗位",
            "地点",
            "薪资",
            "经验",
            "学历",
            "公司规模",
            "融资阶段",
            "行业",
            "匹配度",
            "推荐等级",
            "岗位链接",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.rank,
                row.company,
                row.job_title,
                row.location,
                row.salary,
                row.experience,
                row.education,
                row.company_scale,
                row.company_stage,
                row.company_industry,
                row.match_score,
                row.recommendation_level,
                row.job_url,
            ]
        )
    return buffer.getvalue()


def _overview_row(result: JobMatchResult, job: NormalizedJobPost | None) -> JobOverviewRow:
    return JobOverviewRow(
        rank=result.rank,
        company=_value(job.company if job else None),
        job_title=_value(job.job_title if job else None),
        location=_value(job.location if job else None),
        salary=_value(job.salary if job else None),
        experience=_value(job.experience_required if job else None),
        education=_value(job.education_required if job else None),
        company_scale=_value(job.company_scale if job else None),
        company_stage=_value(job.company_stage if job else None),
        company_industry=_value(job.company_industry if job else None),
        match_score=result.match_score,
        recommendation_level=result.recommendation_level,
        job_url=_job_link(job),
    )


def _render_markdown(
    *,
    run_id: str,
    total_jobs: int,
    ranked: list[JobMatchResult],
    overview: list[JobOverviewRow],
    jobs_by_id: dict[str, NormalizedJobPost],
    skill_report: SkillAnalysisReport | None,
    priority_count: int,
) -> str:
    lines: list[str] = []
    lines.append("# 简历-岗位匹配分析报告")
    lines.append("")
    lines.append(f"- 运行 ID: `{run_id}`")
    lines.append(f"- 分析岗位数: {total_jobs}")
    lines.append(f"- 产出匹配结果: {len(ranked)}")
    lines.append(f"- 优先投递岗位: {priority_count}")
    lines.append("")

    # 1. 总体匹配结论
    lines.append("## 一、总体匹配结论")
    lines.append("")
    lines.append(_overall_conclusion(ranked, priority_count))
    lines.append("")

    # 2. 推荐投递总览表
    lines.append("## 二、推荐投递总览")
    lines.append("")
    lines.extend(_overview_table(overview))
    lines.append("")

    # 3. 每个优先岗位详情卡片
    lines.append("## 三、优先岗位详情")
    lines.append("")
    priority_results = [r for r in ranked if r.recommendation_level == PRIORITY_LEVEL]
    detail_targets = priority_results or ranked[:3]
    if not detail_targets:
        lines.append("暂无可展示的岗位。")
        lines.append("")
    for result in detail_targets:
        lines.extend(_job_card(result, jobs_by_id.get(result.source_job_id)))
        lines.append("")

    # 4. 高频技能画像
    lines.append("## 四、高频技能画像")
    lines.append("")
    lines.extend(_skill_profile(skill_report))
    lines.append("")

    # 5. 简历改写建议
    lines.append("## 五、简历改写建议")
    lines.append("")
    lines.extend(_aggregated_bullets(ranked, lambda r: r.resume_suggestions))
    lines.append("")

    # 6. 面试准备重点
    lines.append("## 六、面试准备重点")
    lines.append("")
    lines.extend(_aggregated_bullets(ranked, lambda r: r.interview_focus))
    lines.append("")

    # 7. 投递策略
    lines.append("## 七、投递策略")
    lines.append("")
    lines.extend(_delivery_strategy(ranked))
    lines.append("")

    return "\n".join(lines)


def _overall_conclusion(ranked: list[JobMatchResult], priority_count: int) -> str:
    if not ranked:
        return "本次没有产出结构化匹配结果，请检查简历文本和岗位样本是否为空。"
    top = ranked[0]
    avg = round(sum(r.match_score for r in ranked) / len(ranked))
    return (
        f"本次共分析 {len(ranked)} 个岗位，平均匹配度 {avg} 分，"
        f"其中 {priority_count} 个岗位达到“优先投递”。"
        f"匹配度最高的是排名第 1 的岗位（{top.match_score} 分，{top.recommendation_level}）。"
    )


def _overview_table(overview: list[JobOverviewRow]) -> list[str]:
    if not overview:
        return ["暂无匹配岗位。"]
    header = (
        "| 排名 | 公司 | 岗位 | 地点 | 薪资 | 经验 | 学历 | 公司规模 | 融资阶段 | 行业 | 匹配度 | 推荐等级 | 岗位链接 |"
    )
    sep = "| --- " * 13 + "|"
    rows = [header, sep]
    for row in overview:
        link = f"[链接]({row.job_url})" if row.job_url != "未提供" else "未提供"
        rows.append(
            f"| {row.rank} | {row.company} | {row.job_title} | {row.location} | {row.salary} "
            f"| {row.experience} | {row.education} | {row.company_scale} | {row.company_stage} "
            f"| {row.company_industry} | {row.match_score} | {row.recommendation_level} | {link} |"
        )
    return rows


def _job_card(result: JobMatchResult, job: NormalizedJobPost | None) -> list[str]:
    title = job.job_title if job else result.source_job_id
    lines = [f"### {result.rank}. {title}（{result.match_score} 分 · {result.recommendation_level}）"]
    lines.append("")
    lines.append(f"- 公司: {_value(job.company if job else None)}")
    lines.append(f"- 岗位: {_value(job.job_title if job else None)}")
    lines.append(f"- 地点: {_value(job.location if job else None)}")
    lines.append(f"- 地址: {_value(job.address if job else None)}")
    lines.append(f"- 薪资: {_value(job.salary if job else None)}")
    lines.append(f"- 公司规模: {_value(job.company_scale if job else None)}")
    lines.append(f"- 融资阶段: {_value(job.company_stage if job else None)}")
    lines.append(f"- 行业: {_value(job.company_industry if job else None)}")
    lines.append(f"- 福利: {_join(job.welfare if job else [])}")
    lines.append(f"- 岗位链接: {_job_link(job)}")
    lines.append(f"- 匹配理由: {_join(result.matched_evidence)}")
    lines.append(f"- 主要短板: {_join(result.gaps)}")
    lines.append(f"- 简历修改建议: {_join(result.resume_suggestions)}")
    lines.append(f"- 面试准备重点: {_join(result.interview_focus)}")
    return lines


def _skill_profile(skill_report: SkillAnalysisReport | None) -> list[str]:
    if skill_report is None or not skill_report.top_skills:
        return ["暂无技能画像数据。"]
    return [
        f"- {skill.name}: 出现 {skill.count} 次，覆盖 {skill.job_count} 个岗位，覆盖率 {skill.coverage:.0%}"
        for skill in skill_report.top_skills
    ]


def _aggregated_bullets(
    ranked: list[JobMatchResult],
    selector,
) -> list[str]:
    seen: set[str] = set()
    bullets: list[str] = []
    for result in ranked:
        for item in selector(result):
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                bullets.append(f"- {cleaned}")
    return bullets or ["- 暂无建议。"]


def _delivery_strategy(ranked: list[JobMatchResult]) -> list[str]:
    if not ranked:
        return ["- 暂无可投递岗位。"]
    priority = [r for r in ranked if r.recommendation_level == PRIORITY_LEVEL]
    normal = [r for r in ranked if r.recommendation_level == "可以投递"]
    cautious = [r for r in ranked if r.recommendation_level == "谨慎投递"]
    return [
        f"- 第一梯队（优先投递，{len(priority)} 个）: 优先准备定制简历和项目讲解，尽快投递。",
        f"- 第二梯队（可以投递，{len(normal)} 个）: 补齐短板后投递，作为主力覆盖面。",
        f"- 第三梯队（谨慎投递，{len(cautious)} 个）: 有余力再投，重点用于练习面试和了解市场。",
    ]


def _value(text: str | None) -> str:
    if text is None:
        return "未提供"
    cleaned = text.strip()
    return cleaned or "未提供"


def _join(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item.strip()]
    return "；".join(cleaned) if cleaned else "未提供"


def _job_link(job: NormalizedJobPost | None) -> str:
    if job is None:
        return "未提供"
    return _value(job.job_url or job.detail_url)
