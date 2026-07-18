from __future__ import annotations

import json
from pathlib import Path

from app.collectors.boss_zhipin_collector import BossCollectionResult, BossZhipinCollector
from app.schemas.run import AgentRun
from app.schemas.workflow import FullJobAgentRequest
from app.services.job_agent_workflow import run_full_job_agent_workflow


FIXTURE = Path(__file__).parent / "fixtures" / "sample_boss_jobs.json"


class FakeCollector:
    """Returns fixture raw jobs without touching subprocess/network."""

    def __init__(self) -> None:
        self.requests: list[str] = []

    def collect_from_request(self, request) -> BossCollectionResult:  # noqa: ANN001
        self.requests.append(request.city)
        raw_jobs = BossZhipinCollector(FIXTURE).collect()
        # Tag city so multi-city collection is visible.
        raw_jobs = [job.model_copy(update={"city": request.city}) for job in raw_jobs]
        run = AgentRun(task_type="boss_collect", city=request.city, status="success").finish_success(
            total_jobs=len(raw_jobs), duration_ms=1
        )
        return BossCollectionResult(raw_jobs=raw_jobs, run=run)

    def fetch_details_for_jobs(self, jobs, **kwargs):  # noqa: ANN001, ANN003
        # Return a detail record per job so the workflow's
        # merge_boss_list_and_detail_jobs path is actually exercised (guards
        # against a missing import silently passing because the merge is skipped).
        self.detail_calls = getattr(self, "detail_calls", 0) + 1
        self.detail_job_counts = getattr(self, "detail_job_counts", [])
        self.detail_job_counts.append(len(jobs))
        return [
            job.model_copy(update={"jd_text": f"详情JD：{job.title} 负责 RAG 与 Agent 编排。"})
            for job in jobs
        ]


class FakeProvider:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        # Return a valid structured result for every job id in the prompt.
        import re

        ids = re.findall(r"岗位ID: (\S+)", prompt)
        results = [
            {
                "source_job_id": job_id,
                "match_score": 90 - index * 10,
                "recommendation_level": "优先投递" if index == 0 else "可以投递",
                "matched_evidence": ["做过 RAG 检索项目"],
                "gaps": ["缺少大规模分布式经验"],
                "resume_suggestions": ["补充 Agent 项目量化指标"],
                "interview_focus": ["讲清 RAG 评估方式"],
            }
            for index, job_id in enumerate(ids)
        ]
        return json.dumps(results, ensure_ascii=False)


def _request(tmp_path: Path, resume: Path, **overrides) -> FullJobAgentRequest:
    base = dict(
        resume_file=str(resume),
        keyword="AI Agent",
        cities=["上海", "深圳"],
        pages=1,
        output_dir=str(tmp_path / "reports"),
        max_jobs=30,
        persist=False,
    )
    base.update(overrides)
    return FullJobAgentRequest(**base)


def test_full_workflow_runs_end_to_end_and_writes_all_artifacts(tmp_path: Path) -> None:
    resume = tmp_path / "resume.txt"
    resume.write_text("做过 Python 后端和 RAG 检索、Agent 编排项目。", encoding="utf-8")
    collector = FakeCollector()
    provider = FakeProvider()

    result = run_full_job_agent_workflow(
        _request(tmp_path, resume),
        collector_factory=lambda req: collector,
        provider_factory=lambda: provider,
    )

    assert result.status == "success"
    assert result.failed_step is None
    assert collector.requests == ["上海", "深圳"]  # both cities collected
    assert result.raw_job_count == 6  # 3 fixture jobs x 2 cities
    assert result.unique_job_count == 3  # deduped by job id across cities
    assert result.matched_job_count == 3
    assert result.priority_job_count == 1
    # The two-phase detail fetch + merge path actually ran (regression guard for
    # the missing merge_boss_list_and_detail_jobs import).
    assert getattr(collector, "detail_calls", 0) == 1

    # All five artifacts + steps trace exist.
    for path in (
        result.artifacts.job_overview_csv,
        result.artifacts.structured_jobs_json,
        result.artifacts.skill_analysis_json,
        result.artifacts.match_results_json,
        result.artifacts.final_report_md,
        result.artifacts.steps_jsonl,
    ):
        assert path is not None
        assert Path(path).exists()

    # Final report carries real metadata.
    report_md = Path(result.artifacts.final_report_md).read_text(encoding="utf-8")
    assert "推荐投递总览" in report_md
    assert "示例智能科技" in report_md
    assert "岗位链接" in report_md

    # Match results JSON is globally ranked.
    match_json = json.loads(Path(result.artifacts.match_results_json).read_text(encoding="utf-8"))
    assert match_json["results"][0]["rank"] == 1
    assert match_json["results"][0]["match_score"] == 90


def test_full_workflow_title_filter_drops_non_matching_jobs(tmp_path: Path) -> None:
    # The fixture has titles like "AI Agent 应用工程师", "大模型算法工程师",
    # "数据后端工程师（Java）". Filtering on "Agent" keeps only the first.
    resume = tmp_path / "resume.txt"
    resume.write_text("做过 Python 后端与 RAG 检索、Agent 编排项目。", encoding="utf-8")
    request = _request(tmp_path, resume, title_filters=["Agent"])

    result = run_full_job_agent_workflow(
        request,
        collector_factory=lambda req: FakeCollector(),
        provider_factory=lambda: FakeProvider(),
        resume_reader=lambda path: resume.read_text(encoding="utf-8"),
    )

    assert result.status == "success"
    assert result.raw_job_count == 6  # 3 fixture jobs x 2 default cities
    assert result.unique_job_count == 1  # deduped to 3, then only "AI Agent" title survives
    assert result.matched_job_count == 1


def test_full_workflow_empty_title_filter_keeps_all(tmp_path: Path) -> None:
    resume = tmp_path / "resume.txt"
    resume.write_text("做过 Python 后端与 RAG 检索、Agent 编排项目。", encoding="utf-8")
    request = _request(tmp_path, resume, title_filters=[])

    result = run_full_job_agent_workflow(
        request,
        collector_factory=lambda req: FakeCollector(),
        provider_factory=lambda: FakeProvider(),
        resume_reader=lambda path: resume.read_text(encoding="utf-8"),
    )

    assert result.unique_job_count == 3


def test_full_workflow_records_all_step_names(tmp_path: Path) -> None:
    resume = tmp_path / "resume.txt"
    resume.write_text("做过 RAG 项目。", encoding="utf-8")

    result = run_full_job_agent_workflow(
        _request(tmp_path, resume),
        collector_factory=lambda req: FakeCollector(),
        provider_factory=lambda: FakeProvider(),
    )

    steps = [
        json.loads(line)
        for line in Path(result.artifacts.steps_jsonl).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    names = [step["name"] for step in steps]
    assert names == [
        "resume_reading",
        "collection",
        "detail_merge",
        "normalization",
        "persistence",
        "jd_structuring",
        "skill_analysis",
        "resume_matching",
        "report_generation",
    ]
    assert all(step["status"] == "success" for step in steps)


def test_full_workflow_empty_resume_fails_at_resume_reading(tmp_path: Path) -> None:
    resume = tmp_path / "resume.txt"
    resume.write_text("   \n  ", encoding="utf-8")  # blank
    collector = FakeCollector()

    result = run_full_job_agent_workflow(
        _request(tmp_path, resume),
        collector_factory=lambda req: collector,
        provider_factory=lambda: FakeProvider(),
    )

    assert result.status == "failed"
    assert result.failed_step == "resume_reading"  # not "collection"
    assert collector.requests == []  # collection never ran


def test_full_workflow_stops_and_reports_failed_step(tmp_path: Path) -> None:
    resume = tmp_path / "resume.txt"
    resume.write_text("做过 RAG 项目。", encoding="utf-8")

    class BrokenProvider:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("model unavailable")

    result = run_full_job_agent_workflow(
        _request(tmp_path, resume),
        collector_factory=lambda req: FakeCollector(),
        provider_factory=lambda: BrokenProvider(),
    )

    assert result.status == "failed"
    assert result.failed_step == "resume_matching"
    assert "model unavailable" in (result.error_message or "")

    # Steps up to the failure are still recorded, with the failure marked.
    steps = [
        json.loads(line)
        for line in Path(result.artifacts.steps_jsonl).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert steps[-1]["name"] == "resume_matching"
    assert steps[-1]["status"] == "failed"
