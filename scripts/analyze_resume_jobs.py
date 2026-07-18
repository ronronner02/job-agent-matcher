from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.schemas.job import NormalizedJobPost, RawJobPost
from app.schemas.jd import StructuredJD
from app.services.ai_resume_job_analyzer import TextGenerationProvider
from app.services.ai_resume_job_analyzer import analyze_resume_against_jobs
from app.services.jd_structurer import structure_jds
from app.services.job_normalizer import normalize_boss_jobs
from app.services.llm_provider import OpenAICompatibleProvider
from app.services.resume_reader import read_resume_text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Use an AI model to compare a private resume with collected jobs."
    )
    parser.add_argument("--resume-file", required=True, help="Private resume PDF/TXT/Markdown file. Do not commit it.")
    parser.add_argument(
        "--jobs",
        required=True,
        nargs="+",
        help="One or more exported BOSS job JSON files, directories, or glob patterns.",
    )
    parser.add_argument("--output", required=True, help="Path to write Markdown analysis report.")
    parser.add_argument("--max-jobs", type=int, default=20, help="Maximum structured jobs to send to the AI model.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Split jobs into smaller AI calls. Use 0 to send one request.",
    )
    args = parser.parse_args()

    resume_text = read_resume_text(args.resume_file)
    job_paths = expand_job_inputs(args.jobs)
    raw_jobs = load_raw_jobs_from_exports(job_paths)
    normalized_jobs = dedupe_normalized_jobs(normalize_boss_jobs(raw_jobs))
    structured_jds = structure_jds(normalized_jobs)

    provider = OpenAICompatibleProvider.from_env()
    report = analyze_resume_jobs_report(
        resume_text,
        structured_jds,
        provider,
        max_jobs=args.max_jobs,
        batch_size=args.batch_size,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(
        f"Wrote AI resume-job analysis to {output_path} "
        f"from {len(job_paths)} files and {len(normalized_jobs)} unique jobs"
    )
    return 0


def expand_job_inputs(values: list[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        for item in value.replace("，", ",").split(","):
            raw = item.strip()
            if not raw:
                continue
            candidate = Path(raw)
            if candidate.is_dir():
                paths.extend(sorted(candidate.glob("*.json")))
                continue
            matches = [Path(match) for match in sorted(glob.glob(raw))] if any(ch in raw for ch in "*?[") else []
            paths.extend(matches or [candidate])

    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        if not resolved.exists():
            raise FileNotFoundError(f"job export not found: {path}")
        if resolved.suffix.lower() != ".json":
            raise ValueError(f"job export must be a JSON file: {path}")
        seen.add(resolved)
        unique_paths.append(resolved)
    if not unique_paths:
        raise ValueError("--jobs did not match any JSON files")
    return unique_paths


def load_raw_jobs_from_exports(paths: list[Path]) -> list[RawJobPost]:
    raw_jobs: list[RawJobPost] = []
    for path in paths:
        raw_jobs.extend(BossZhipinCollector(path).collect())
    return raw_jobs


def dedupe_normalized_jobs(jobs: list[NormalizedJobPost]) -> list[NormalizedJobPost]:
    deduped: dict[tuple[str, str], NormalizedJobPost] = {}
    for job in jobs:
        deduped[(job.platform, job.source_job_id)] = job
    return list(deduped.values())


def analyze_resume_jobs_report(
    resume_text: str,
    structured_jds: list[StructuredJD],
    provider: TextGenerationProvider,
    *,
    max_jobs: int,
    batch_size: int = 0,
) -> str:
    selected = structured_jds[:max_jobs]
    if batch_size <= 0 or batch_size >= len(selected):
        return analyze_resume_against_jobs(
            resume_text,
            selected,
            provider,
            max_jobs=len(selected),
        )

    reports: list[str] = []
    for batch_index, batch in enumerate(_chunks(selected, batch_size), start=1):
        start = (batch_index - 1) * batch_size + 1
        end = start + len(batch) - 1
        batch_report = analyze_resume_against_jobs(
            resume_text,
            batch,
            provider,
            max_jobs=len(batch),
        )
        reports.append(f"## 批次 {batch_index}: 岗位 {start}-{end}\n\n{batch_report.strip()}")

    return "\n\n".join(
        [
            "# 分批 AI 简历-岗位匹配报告",
            "",
            f"共分析 {len(selected)} 个岗位，每批最多 {batch_size} 个岗位。",
            "每个批次内部已经按匹配度排序；如果需要全局最终排序，请优先查看各批次的高分岗位。",
            "",
            *reports,
            "",
        ]
    )


def _chunks(items: list[StructuredJD], size: int) -> list[list[StructuredJD]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    return [items[index : index + size] for index in range(0, len(items), size)]


if __name__ == "__main__":
    raise SystemExit(main())
