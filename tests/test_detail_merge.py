from app.integrations.boss_zhipin.detail_merge import (
    dedupe_raw_jobs,
    merge_boss_list_and_detail_jobs,
)
from app.schemas.job import RawJobPost


def _list_job(**kwargs) -> RawJobPost:
    source_job_id = kwargs.get("source_job_id", "job-1")
    base = dict(
        source_job_id="job-1",
        title="AI 应用工程师",
        company="示例公司",
        location="上海",
        salary="20-35K",
        job_url="https://www.zhipin.com/job_detail/job-1.html",
        skills=["Python"],
        raw_payload={"job_id": source_job_id} if source_job_id else {},
    )
    base.update(kwargs)
    return RawJobPost(**base)


def test_merge_by_source_job_id_adds_detail_fields() -> None:
    list_jobs = [_list_job()]
    detail_jobs = [
        RawJobPost(
            source_job_id="job-1",
            jd_text="负责 RAG 检索链路与工具调用，构建 AI Agent 应用。",
            address="上海市浦东新区张江路 1 号",
            skills=["RAG", "LangGraph"],
            welfare="五险一金",
            detail_url="https://www.zhipin.com/job_detail/job-1.html",
            raw_payload={"job_id": "job-1", "jd": "..."},
        )
    ]

    merged = merge_boss_list_and_detail_jobs(list_jobs, detail_jobs)

    assert len(merged) == 1
    job = merged[0]
    assert "RAG 检索链路" in (job.jd_text or "")
    assert job.address == "上海市浦东新区张江路 1 号"
    assert job.skills == ["Python", "RAG", "LangGraph"]
    assert job.welfare == "五险一金"
    assert job.raw_payload["job_id"] == "job-1"
    assert "detail_raw_payload" in job.raw_payload


def test_merge_keeps_list_job_when_no_detail_matches() -> None:
    list_jobs = [_list_job(source_job_id="job-1"), _list_job(source_job_id="job-2")]
    detail_jobs = [
        RawJobPost(source_job_id="job-1", jd_text="有详情", raw_payload={"job_id": "job-1"})
    ]

    merged = merge_boss_list_and_detail_jobs(list_jobs, detail_jobs)

    assert len(merged) == 2
    assert merged[0].jd_text == "有详情"
    assert merged[1].jd_text is None  # untouched, not dropped


def test_merge_falls_back_to_url_then_composite() -> None:
    by_url = _list_job(source_job_id=None, raw_payload={})
    detail_url = RawJobPost(
        job_url="https://www.zhipin.com/job_detail/job-1.html",
        jd_text="URL 匹配详情",
    )

    merged = merge_boss_list_and_detail_jobs([by_url], [detail_url])
    assert merged[0].jd_text == "URL 匹配详情"

    by_composite = _list_job(source_job_id=None, job_url=None, raw_payload={})
    detail_composite = RawJobPost(
        company="示例公司",
        title="AI 应用工程师",
        location="上海",
        jd_text="公司标题地点匹配详情",
    )

    merged = merge_boss_list_and_detail_jobs([by_composite], [detail_composite])
    assert merged[0].jd_text == "公司标题地点匹配详情"


def test_merge_prefers_more_complete_detail_jd() -> None:
    list_jobs = [_list_job(jd_text="短")]
    detail_jobs = [
        RawJobPost(source_job_id="job-1", jd_text="更完整更长的岗位描述文本内容", raw_payload={"job_id": "job-1"})
    ]

    merged = merge_boss_list_and_detail_jobs(list_jobs, detail_jobs)
    assert merged[0].jd_text == "更完整更长的岗位描述文本内容"


def test_dedupe_raw_jobs_collapses_same_job_across_cities() -> None:
    # Same job id appears in two city collections; keep the more complete one.
    thin = _list_job(source_job_id="job-1", jd_text=None)
    rich = _list_job(source_job_id="job-1", jd_text="更完整的岗位描述")
    other = _list_job(source_job_id="job-2", job_url="https://www.zhipin.com/job_detail/job-2.html")

    deduped = dedupe_raw_jobs([thin, rich, other])

    ids = sorted(job.source_job_id for job in deduped)
    assert ids == ["job-1", "job-2"]
    kept = next(job for job in deduped if job.source_job_id == "job-1")
    assert kept.jd_text == "更完整的岗位描述"


def test_dedupe_raw_jobs_keeps_distinct_jobs() -> None:
    first = _list_job(source_job_id="job-1")
    second = _list_job(
        source_job_id="job-2",
        job_url="https://www.zhipin.com/job_detail/job-2.html",
        raw_payload={"job_id": "job-2"},
    )

    deduped = dedupe_raw_jobs([first, second])

    assert len(deduped) == 2
