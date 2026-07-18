from __future__ import annotations

from app.collectors.boss_zhipin_collector import BossCollectionResult, BossZhipinCollector
from app.schemas.collect import CollectionRequest


def collect_boss_jobs(
    request: CollectionRequest,
    collector: BossZhipinCollector | None = None,
) -> BossCollectionResult:
    """Application-level collection entrypoint.

    FastAPI routing will wrap this function later; keeping it framework-free now
    lets the collector contract stabilize before adding HTTP concerns.
    """

    active_collector = collector or BossZhipinCollector()
    return active_collector.collect_from_request(request)
