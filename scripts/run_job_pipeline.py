from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.pipeline_service import run_offline_job_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the offline job analysis pipeline from exported BOSS JSON."
    )
    parser.add_argument("input", help="Path to a boss-zhipin-scraper JSON export.")
    parser.add_argument("--database-url", default=None, help="SQLAlchemy database URL.")
    parser.add_argument("--output-dir", default="data/reports", help="Directory for generated reports.")
    parser.add_argument("--top", type=int, default=10, help="Number of top skills to include.")
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Skip SQLite persistence and only generate structured/report artifacts.",
    )
    args = parser.parse_args()

    result = run_offline_job_pipeline(
        args.input,
        database_url=args.database_url,
        output_dir=args.output_dir,
        persist=not args.no_persist,
        top_n=args.top,
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
