from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.collectors.boss_zhipin_collector import BossCollectionResult
from app.schemas.collect import CollectionRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect BOSS jobs through the project adapter.")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--city", default="广州")
    parser.add_argument("--cities", help="Comma-separated cities, for example: 广州,深圳,东莞,佛山,惠州,中山")
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--scraper-root")
    parser.add_argument("--output-dir", default="data/raw_jobs")
    # Debug collection defaults to list-only: detail pages are ~30s each, so a
    # quick "did the scraper work?" run should not silently crawl details.
    parser.add_argument(
        "--include-detail",
        dest="include_detail",
        action="store_true",
        default=False,
        help="Also fetch detail-page JD (slow: ~30s per job).",
    )
    parser.add_argument(
        "--no-detail",
        dest="include_detail",
        action="store_false",
        help="List-only collection (default for this debug script).",
    )
    args = parser.parse_args()

    collector = BossZhipinCollector(
        scraper_root=args.scraper_root,
        output_dir=args.output_dir,
    )
    cities = parse_cities(args.cities) if args.cities else [args.city.strip()]
    results = collect_for_cities(
        collector,
        keyword=args.keyword,
        cities=cities,
        pages=args.pages,
        cdp_port=args.cdp_port,
        include_detail=args.include_detail,
    )
    payload = {
        "keyword": args.keyword,
        "cities": cities,
        "total_jobs": sum(result.run.total_jobs for result in results),
        "success_count": sum(result.run.success_count for result in results),
        "runs": [result.run.model_dump(mode="json") for result in results],
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if all(result.run.status == "success" for result in results) else 2


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


def collect_for_cities(
    collector: BossZhipinCollector,
    *,
    keyword: str,
    cities: list[str],
    pages: int,
    cdp_port: int,
    include_detail: bool = False,
) -> list[BossCollectionResult]:
    results: list[BossCollectionResult] = []
    for city in cities:
        request = CollectionRequest(
            keyword=keyword,
            city=city,
            pages=pages,
            cdp_port=cdp_port,
            include_detail=include_detail,
        )
        results.append(collector.collect_from_request(request))
    return results


if __name__ == "__main__":
    raise SystemExit(main())
