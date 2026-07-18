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


def main() -> int:
    parser = argparse.ArgumentParser(description="Structure JD text from a boss-zhipin-scraper JSON export.")
    parser.add_argument("input", help="Path to boss-zhipin-scraper JSON export.")
    parser.add_argument("--output", required=True, help="Path to write structured JD JSON.")
    args = parser.parse_args()

    raw_jobs = BossZhipinCollector(args.input).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)
    structured = structure_jds(normalized_jobs)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in structured], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Structured {len(structured)} JDs to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
