from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import session_scope
from app.repositories.job_repository import get_jobs_by_source_ids
from app.repositories.match_repository import save_match_report
from app.schemas.jd import StructuredJD
from app.schemas.job import NormalizedJobPost
from app.schemas.match import JobMatchReport
from app.schemas.skill import SkillAnalysisReport
from app.services.report_generator import build_final_report, build_overview_csv
from app.services.resume_job_matcher import (
    TextGenerationProvider,
    build_match_contexts,
    match_resume_against_jobs,
)
from app.services.resume_reader import read_resume_text


PROVIDER_HINT = (
    "AI provider 调用失败。可以尝试：\n"
    "  - 降低 --batch-size（例如 --batch-size 1），减少单次请求体积；\n"
    "  - 提高 AI_MATCHER_TIMEOUT_SECONDS（慢模型或中转服务需要更久）；\n"
    "  - 检查中转服务 / API Key / base_url 是否可用。"
)


class ResumeError(Exception):
    """A resume-continuation failure with a user-facing message."""


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resume a failed full-job-agent run at the resume_matching step, "
            "reusing the structured jobs and skill analysis already produced. "
            "Does NOT re-collect or re-scrape."
        ),
    )
    parser.add_argument("--run-id", required=True, help="The run_id of the failed run to resume.")
    parser.add_argument("--resume-file", required=True, help="Private resume PDF/TXT/Markdown.")
    parser.add_argument("--output-dir", default="data/reports")
    parser.add_argument("--database-url", default=None, help="SQLAlchemy URL for job metadata.")
    parser.add_argument("--max-jobs", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=3, help="AI batch size (default 3, use 1 if unstable).")
    args = parser.parse_args()

    try:
        result = resume_full_job_agent(
            run_id=args.run_id,
            resume_file=args.resume_file,
            output_dir=args.output_dir,
            database_url=args.database_url,
            max_jobs=args.max_jobs,
            batch_size=args.batch_size,
        )
    except ResumeError as exc:
        print(f"\n[FAILED] {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        f"\n[OK] 续跑 {args.run_id}: {result['matched_job_count']} 个匹配, "
        f"{result['priority_job_count']} 个优先投递\n最终报告: {result['final_report_md']}"
    )
    return 0


def resume_full_job_agent(
    *,
    run_id: str,
    resume_file: str,
    output_dir: str = "data/reports",
    database_url: str | None = None,
    max_jobs: int = 60,
    batch_size: int = 3,
    provider: TextGenerationProvider | None = None,
    resume_reader=read_resume_text,
) -> dict:
    """Continue a failed run from resume_matching, reusing prior artifacts.

    Reads ``{run_id}_structured_jobs.json`` and ``{run_id}_skill_analysis.json``
    from ``output_dir`` and reconstructs the NormalizedJobPost metadata from the
    database, then runs matching + report generation. The original ``run_id`` is
    reused so all artifacts line up with the earlier run. Collection, normalization
    and structuring are never re-run.
    """

    out_dir = Path(output_dir)
    structured_path = out_dir / f"{run_id}_structured_jobs.json"
    skill_path = out_dir / f"{run_id}_skill_analysis.json"

    structured_jds = _load_structured_jds(structured_path)
    skill_report = _load_skill_report(skill_path)

    resume_text = resume_reader(resume_file)
    if not resume_text.strip():
        raise ResumeError(f"简历为空或无法读取: {resume_file}")

    source_ids = [jd.source_job_id for jd in structured_jds]
    normalized_jobs = _load_jobs_from_db(source_ids, database_url)
    if not normalized_jobs:
        raise ResumeError(
            "数据库中找不到该 run 的岗位元信息。请确认 --database-url 指向当初入库的数据库。"
        )

    contexts = build_match_contexts(normalized_jobs, structured_jds)
    if not contexts:
        raise ResumeError("结构化岗位与数据库岗位无法配对（source_job_id 不匹配）。")

    active_provider = provider if provider is not None else _default_provider()

    try:
        report = match_resume_against_jobs(
            resume_text,
            contexts,
            active_provider,
            run_id=run_id,
            max_jobs=max_jobs,
            batch_size=batch_size,
        )
    except Exception as exc:  # AI provider connection / parsing failure
        raise ResumeError(f"{exc}\n\n{PROVIDER_HINT}") from exc

    # Persist match results if we have a database to write to.
    if database_url is not None:
        with session_scope(database_url) as session:
            save_match_report(session, report)

    match_path = out_dir / f"{run_id}_match_results.json"
    overview_path = out_dir / f"{run_id}_job_overview.csv"
    report_path = out_dir / f"{run_id}_final_report.md"

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(match_path, report.model_dump(mode="json"))

    jobs_by_id = {job.source_job_id: job for job in normalized_jobs}
    final = build_final_report(report, jobs_by_id, skill_report)
    overview_path.write_text(build_overview_csv(final.overview), encoding="utf-8-sig")
    report_path.write_text(final.markdown, encoding="utf-8")

    return {
        "run_id": run_id,
        "matched_job_count": len(report.results),
        "priority_job_count": final.priority_jobs,
        "match_results_json": str(match_path),
        "job_overview_csv": str(overview_path),
        "final_report_md": str(report_path),
    }


def _load_structured_jds(path: Path) -> list[StructuredJD]:
    if not path.exists():
        raise ResumeError(f"找不到结构化岗位文件: {path}（请确认 run_id 和 --output-dir）")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ResumeError(f"结构化岗位文件格式异常（应为数组）: {path}")
    return [StructuredJD.model_validate(item) for item in data]


def _load_skill_report(path: Path) -> SkillAnalysisReport | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return SkillAnalysisReport.model_validate(data)


def _load_jobs_from_db(source_ids: list[str], database_url: str | None) -> list[NormalizedJobPost]:
    with session_scope(database_url) as session:
        by_id = get_jobs_by_source_ids(session, source_ids)
    # Preserve the structured-jobs order; skip ids missing from the DB.
    return [by_id[sid] for sid in source_ids if sid in by_id]


def _default_provider() -> TextGenerationProvider:
    from app.services.llm_provider import OpenAICompatibleProvider

    return OpenAICompatibleProvider.from_env()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
