from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.workflow import FullJobAgentRequest
from app.services.job_agent_workflow import run_full_job_agent_workflow


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the full job agent: collect -> merge -> match -> report, in one command.",
    )
    parser.add_argument("--resume-file", required=True, help="Private resume PDF/TXT/Markdown. Do not commit it.")
    parser.add_argument("--keyword", required=True, help="Search keyword, e.g. 'AI Agent'.")
    parser.add_argument("--cities", default="上海", help="Comma-separated cities, e.g. 上海,深圳,广州.")
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--scraper-root", default=None, help="Path to boss-zhipin-scraper checkout.")
    parser.add_argument("--output-dir", default="data/reports")
    parser.add_argument("--max-jobs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=0, help="Split AI matching into batches. 0 = one call.")
    parser.add_argument("--max-details", type=int, default=None, help="Cap detail-page fetches per city.")
    parser.add_argument(
        "--title-contains",
        default=None,
        help="Comma-separated terms; keep only jobs whose title contains one (BOSS search is fuzzy).",
    )
    parser.add_argument("--include-detail", dest="include_detail", action="store_true", default=True)
    parser.add_argument("--no-detail", dest="include_detail", action="store_false")
    parser.add_argument("--no-persist", action="store_true", help="Skip SQLite persistence.")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    request = FullJobAgentRequest(
        resume_file=args.resume_file,
        keyword=args.keyword,
        cities=parse_cities(args.cities),
        pages=args.pages,
        cdp_port=args.cdp_port,
        scraper_root=args.scraper_root,
        output_dir=args.output_dir,
        max_jobs=args.max_jobs,
        batch_size=args.batch_size,
        max_details=args.max_details,
        title_filters=parse_cities(args.title_contains) if args.title_contains else [],
        include_detail=args.include_detail,
        persist=not args.no_persist,
        database_url=args.database_url,
    )

    result = run_full_job_agent_workflow(request)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if result.status != "success":
        print(f"\n[FAILED] step={result.failed_step}: {result.error_message}", file=sys.stderr)
        return 2
    print(
        f"\n[OK] run {result.run_id}: {result.unique_job_count} 个岗位, "
        f"{result.priority_job_count} 个优先投递\n最终报告: {result.artifacts.final_report_md}"
    )
    return 0


def parse_cities(value: str) -> list[str]:
    cities: list[str] = []
    seen: set[str] = set()
    for item in value.replace("，", ",").split(","):
        city = item.strip()
        if city and city not in seen:
            seen.add(city)
            cities.append(city)
    if not cities:
        raise ValueError("--cities must contain at least one city")
    return cities


if __name__ == "__main__":
    raise SystemExit(main())
