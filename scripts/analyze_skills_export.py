from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.services.jd_structurer import structure_jds
from app.services.job_normalizer import normalize_boss_jobs
from app.services.skill_analyzer import analyze_skills


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze skill requirements from a boss-zhipin-scraper JSON export.")
    parser.add_argument("input", help="Path to boss-zhipin-scraper JSON export.")
    parser.add_argument("--output", required=True, help="Path to write skill analysis JSON.")
    parser.add_argument("--top", type=int, default=10, help="Number of top skills to include.")
    args = parser.parse_args()

    raw_jobs = BossZhipinCollector(args.input).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)
    structured_jds = structure_jds(normalized_jobs)
    report = analyze_skills(structured_jds, top_n=args.top)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Analyzed {report.total_jobs} jobs to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
