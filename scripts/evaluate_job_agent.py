from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.integrations.boss_zhipin.detail_merge import merge_boss_list_and_detail_jobs
from app.services.evaluation import (
    average_task_latency_seconds,
    collection_success_rate,
    field_completeness,
    match_explanation_validity,
    skill_tag_scores,
)
from app.services.jd_structurer import structure_jds
from app.services.job_normalizer import normalize_boss_jobs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate real job-agent exports without fabricating unavailable labels."
    )
    parser.add_argument("--jobs", nargs="+", required=True, help="Raw BOSS JSON export(s).")
    parser.add_argument("--run-log", default="data/runs/agent_runs.jsonl")
    parser.add_argument("--details", nargs="+", help="Optional detail-page JSON export(s).")
    parser.add_argument("--match-results", help="A match_results.json or compatible JSON report.")
    parser.add_argument(
        "--match-job-ids",
        nargs="+",
        help="Expected IDs for the match sample; use this when matching only a subset of --jobs.",
    )
    parser.add_argument(
        "--skill-gold",
        help="JSON object mapping source_job_id to independently labelled skill names.",
    )
    parser.add_argument("--output", default="data/reports/evaluation.json")
    parser.add_argument("--markdown-output", default=None)
    args = parser.parse_args()

    jobs = load_jobs(args.jobs)
    detail_jobs = load_jobs(args.details or [])
    evaluated_jobs = merge_boss_list_and_detail_jobs(jobs, detail_jobs) if detail_jobs else jobs
    runs = load_jsonl(Path(args.run_log)) if Path(args.run_log).exists() else []
    runs = select_runs_for_exports(runs, args.jobs)
    matches = load_match_results(Path(args.match_results)) if args.match_results else []

    normalized = normalize_boss_jobs(evaluated_jobs)
    structured = structure_jds(normalized)
    predicted_skills = {
        jd.source_job_id: [skill.name for skill in jd.skills] for jd in structured
    }
    gold = load_skill_gold(Path(args.skill_gold)) if args.skill_gold else {}
    skill_scores = skill_tag_scores(predicted_skills, gold)
    job_ids = set(args.match_job_ids or [])
    if not job_ids:
        job_ids = {job.source_job_id or "" for job in normalized if job.source_job_id}

    report: dict[str, Any] = {
        "evaluation_scope": {
            "job_export_files": [str(Path(path).resolve()) for path in args.jobs],
            "raw_job_count": len(jobs),
            "normalized_job_count": len(normalized),
            "detail_job_count": len(detail_jobs),
            "collection_task_count": sum(
                1 for run in runs if run.get("task_type") == "boss_collect"
            ),
            "match_result_count": len(matches),
            "match_expected_job_count": len(job_ids),
        },
        "metrics": {
            "job_collection_success_rate": collection_success_rate(runs),
            "field_completeness_rate": field_completeness(
                [job.model_dump(mode="json") for job in jobs]
            ),
            "detail_jd_completeness_rate": (
                field_completeness(
                    [job.model_dump(mode="json") for job in detail_jobs],
                    fields=("source_job_id", "jd_text"),
                )
                if detail_jobs
                else None
            ),
            "skill_tag_accuracy": skill_scores["accuracy"],
            "skill_tag_precision": skill_scores["precision"],
            "skill_tag_recall": skill_scores["recall"],
            "match_explanation_validity": match_explanation_validity(matches, job_ids),
            "avg_task_latency_seconds": average_task_latency_seconds(runs),
        },
        "metric_notes": {
            "field_completeness_rate": "7 list-page fields: source_job_id, title, company, location, salary, tags, job_url.",
            "detail_jd_completeness_rate": "Among supplied detail exports, source_job_id and jd_text are both non-empty.",
            "skill_tag_accuracy": (
                "micro-F1 against independent --skill-gold reference labels; null means no labels were supplied."
            ),
            "match_explanation_validity": (
                "structural coverage check for matched_evidence, gaps, resume_suggestions and interview_focus; "
                "it does not prove semantic correctness. When --match-job-ids is provided, the denominator is that sample."
            ),
            "avg_task_latency_seconds": "Mean duration_ms of boss_collect records in --run-log.",
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_output:
        markdown = Path(args.markdown_output)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def load_jobs(paths: list[str]) -> list[Any]:
    jobs = []
    seen: set[tuple[str, str]] = set()
    for value in paths:
        path = Path(value)
        candidates = sorted(path.glob("*.json")) if path.is_dir() else [path]
        for candidate in candidates:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            rows = payload.get("jobs", []) if isinstance(payload, dict) else payload
            for row in BossZhipinCollector._extract_job_rows(rows):
                key = (str(row.get("job_id") or row.get("encrypt_job_id") or ""), str(row.get("job_link") or row.get("job_url") or ""))
                if key != ("", "") and key in seen:
                    continue
                seen.add(key)
                jobs.append(BossZhipinCollector._to_raw_job(row, keyword=payload.get("keyword") if isinstance(payload, dict) else None, city=payload.get("city") if isinstance(payload, dict) else None))
    return jobs


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def select_runs_for_exports(
    runs: list[dict[str, Any]],
    export_paths: list[str],
) -> list[dict[str, Any]]:
    """Keep run-log entries that produced one of the evaluated exports.

    The default run log is append-only, so using every historical collection
    would silently contaminate a point-in-time evaluation. If no exact path
    match exists, return all records so custom logs still work as expected.
    """

    expected = {str(Path(path).resolve()).lower() for path in export_paths}
    selected = {
        str(Path(str(run.get("raw_output_path"))).resolve()).lower(): run
        for run in runs
        if run.get("raw_output_path")
    }
    matched = [run for path, run in selected.items() if path in expected]
    return matched or runs


def load_match_results(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("results", [])
    return payload if isinstance(payload, list) else []


def load_skill_gold(path: Path) -> dict[str, list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("jobs"), dict):
        payload = payload["jobs"]
    return payload if isinstance(payload, dict) else {}


def render_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# Job Agent Evaluation",
        "",
        f"真实岗位样本数：{report['evaluation_scope']['raw_job_count']}",
        f"采集任务数：{report['evaluation_scope']['collection_task_count']}",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
    ]
    for name, value in metrics.items():
        display = "未评估" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)
        lines.append(f"| {name} | {display} |")
    lines.extend(["", "## 口径", ""])
    lines.extend(f"- {key}: {value}" for key, value in report["metric_notes"].items())
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
