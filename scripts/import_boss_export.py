from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.db.session import session_scope
from app.services.job_normalizer import normalize_boss_jobs
from app.repositories.job_repository import upsert_normalized_jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Import boss-zhipin-scraper JSON into SQLite.")
    parser.add_argument("input", help="Path to boss-zhipin-scraper JSON export.")
    parser.add_argument("--database-url", default=None, help="SQLAlchemy database URL.")
    args = parser.parse_args()

    raw_jobs = BossZhipinCollector(args.input).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)
    with session_scope(args.database_url) as session:
        saved = upsert_normalized_jobs(session, normalized_jobs)
        print(f"Imported {len(saved)} jobs into database")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
