from __future__ import annotations

from pathlib import Path

import pytest

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.schemas.match import JobMatchResult
from app.services.jd_structurer import structure_jds
from app.services.job_normalizer import normalize_boss_jobs
from app.services.resume_job_matcher import (
    JobMatchContext,
    build_match_contexts,
    build_match_prompt,
    match_resume_against_jobs,
    parse_match_results,
    rank_match_results,
)


FIXTURE = Path(__file__).parent / "fixtures" / "sample_boss_jobs.json"


def _contexts() -> list[JobMatchContext]:
    raw_jobs = BossZhipinCollector(FIXTURE).collect()
    normalized = normalize_boss_jobs(raw_jobs)
    structured = structure_jds(normalized)
    return build_match_contexts(normalized, structured)


class ScriptedProvider:
    """Returns a queued response per call so batching can be tested."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def test_parse_match_results_reads_plain_json_array() -> None:
    raw = (
        '[{"source_job_id": "a", "match_score": 80, '
        '"recommendation_level": "优先投递", "matched_evidence": ["会 Python"]}]'
    )
    results = parse_match_results(raw)

    assert len(results) == 1
    assert results[0].source_job_id == "a"
    assert results[0].match_score == 80
    assert results[0].matched_evidence == ["会 Python"]


def test_parse_match_results_strips_markdown_fence_and_results_key() -> None:
    raw = """```json
{"results": [{"source_job_id": "x", "match_score": 55}]}
```"""
    results = parse_match_results(raw)

    assert len(results) == 1
    assert results[0].source_job_id == "x"
    # Default recommendation level applies when the model omits it.
    assert results[0].recommendation_level == "谨慎投递"


def test_parse_match_results_returns_empty_on_garbage() -> None:
    assert parse_match_results("模型今天不想输出 JSON") == []


def test_rank_match_results_sorts_by_score_then_level_then_gaps() -> None:
    results = [
        JobMatchResult(source_job_id="low", match_score=40, recommendation_level="谨慎投递"),
        JobMatchResult(source_job_id="high", match_score=90, recommendation_level="优先投递"),
        JobMatchResult(
            source_job_id="mid-a",
            match_score=70,
            recommendation_level="可以投递",
            gaps=["缺 A", "缺 B"],
        ),
        JobMatchResult(
            source_job_id="mid-b",
            match_score=70,
            recommendation_level="可以投递",
            gaps=["缺 A"],
        ),
    ]

    ranked = rank_match_results(results)

    assert [r.source_job_id for r in ranked] == ["high", "mid-b", "mid-a", "low"]
    assert [r.rank for r in ranked] == [1, 2, 3, 4]


def test_match_resume_globally_ranks_across_batches() -> None:
    contexts = _contexts()
    ids = [ctx.job.source_job_id for ctx in contexts]
    assert len(ids) >= 3

    # With batch_size=1 each job is its own batch. The last batch returns the
    # highest score; a correct global sort must place it first even though it
    # arrived from a later batch.
    batch1 = f'[{{"source_job_id": "{ids[0]}", "match_score": 30, "recommendation_level": "谨慎投递"}}]'
    batch2 = f'[{{"source_job_id": "{ids[1]}", "match_score": 55, "recommendation_level": "可以投递"}}]'
    batch3 = f'[{{"source_job_id": "{ids[2]}", "match_score": 95, "recommendation_level": "优先投递"}}]'
    provider = ScriptedProvider([batch1, batch2, batch3])

    report = match_resume_against_jobs(
        "做过 Python 后端与 RAG 检索项目。",
        contexts,
        provider,
        run_id="run-test",
        max_jobs=3,
        batch_size=1,
    )

    assert report.run_id == "run-test"
    assert report.total_jobs == 3
    assert len(provider.prompts) == 3  # 3 jobs, batch_size=1
    assert report.results[0].source_job_id == ids[2]
    assert report.results[0].rank == 1
    assert report.results[0].match_score == 95


def test_match_prompt_contains_job_metadata_and_grounding() -> None:
    contexts = _contexts()
    prompt = build_match_prompt("熟悉 Python、RAG。", contexts[:1])

    assert "不要编造经历" in prompt
    assert "岗位ID" in prompt
    assert "公司规模" in prompt
    assert "融资阶段" in prompt
    assert "岗位链接" in prompt
    assert contexts[0].job.source_job_id in prompt


def test_match_rejects_blank_resume() -> None:
    with pytest.raises(ValueError, match="resume_text"):
        match_resume_against_jobs("   ", _contexts(), ScriptedProvider(["[]"]), run_id="r")
