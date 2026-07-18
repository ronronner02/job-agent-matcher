from __future__ import annotations

import json
from pathlib import Path

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.db.session import session_scope
from app.schemas.pipeline import PipelineArtifacts, PipelineResult
from app.schemas.skill import SkillAnalysisReport
from app.services.jd_structurer import structure_jds
from app.services.job_normalizer import normalize_boss_jobs
from app.repositories.job_repository import upsert_normalized_jobs
from app.services.skill_analyzer import analyze_skills


def run_offline_job_pipeline(
    input_path: str | Path,
    *,
    database_url: str | None = None,
    output_dir: str | Path = "data/reports",
    persist: bool = True,
    top_n: int = 10,
) -> PipelineResult:
    """Run the offline job-analysis pipeline on an exported JSON file."""

    input_file = Path(input_path)
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    raw_jobs = BossZhipinCollector(input_file).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)

    saved_count = 0
    if persist:
        with session_scope(database_url) as session:
            saved_count = len(upsert_normalized_jobs(session, normalized_jobs))

    structured_jds = structure_jds(normalized_jobs)
    skill_report = analyze_skills(structured_jds, top_n=top_n)

    stem = input_file.stem
    structured_path = report_dir / f"{stem}_structured_jds.json"
    skill_report_path = report_dir / f"{stem}_skill_analysis.json"
    markdown_path = report_dir / f"{stem}_pipeline_report.md"

    _write_json(structured_path, [jd.model_dump(mode="json") for jd in structured_jds])
    _write_json(skill_report_path, skill_report.model_dump(mode="json"))
    markdown_path.write_text(
        build_pipeline_markdown_report(skill_report),
        encoding="utf-8",
    )

    return PipelineResult(
        raw_job_count=len(raw_jobs),
        normalized_job_count=len(normalized_jobs),
        saved_job_count=saved_count,
        structured_jd_count=len(structured_jds),
        top_skill_names=[skill.name for skill in skill_report.top_skills],
        database_url=database_url if persist else None,
        artifacts=PipelineArtifacts(
            structured_jds_path=structured_path,
            skill_report_path=skill_report_path,
            markdown_report_path=markdown_path,
        ),
    )


def build_pipeline_markdown_report(report: SkillAnalysisReport) -> str:
    """Create a human-readable report for interview review and resume updates."""

    lines = [
        "# AI 岗位技能分析报告",
        "",
        f"{report.summary}",
        "",
        "## 高频技能",
        "",
    ]
    if report.top_skills:
        lines.extend(
            f"- {skill.name}: 出现 {skill.count} 次，覆盖 {skill.job_count} 个岗位，覆盖率 {skill.coverage:.0%}"
            for skill in report.top_skills
        )
    else:
        lines.append("- 暂无可统计技能。")

    lines.extend(["", "## 技能类别", ""])
    if report.category_distribution:
        lines.extend(
            f"- {item.category}: {item.skill_count} 个技能，{item.mention_count} 次提及，覆盖率 {item.coverage:.0%}"
            for item in report.category_distribution
        )
    else:
        lines.append("- 暂无技能类别分布。")

    lines.extend(["", "## 学习建议", ""])
    if report.recommendations:
        lines.extend(f"- {item}" for item in report.recommendations)
    else:
        lines.append("- 先补充更多岗位样本，再生成针对性建议。")

    lines.append("")
    return "\n".join(lines)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
