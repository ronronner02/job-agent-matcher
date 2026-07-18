import json
from pathlib import Path

import pytest

from app.schemas.job import NormalizedJobPost
from app.services.jd_structurer import structure_jds
from scripts.analyze_resume_jobs import (
    analyze_resume_jobs_report,
    dedupe_normalized_jobs,
    expand_job_inputs,
    load_raw_jobs_from_exports,
)


class FakeProvider:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "# 批次匹配报告\n\n| 排名 | 岗位ID | 匹配度百分比 |"


def test_expand_job_inputs_accepts_files_directories_globs_and_commas(tmp_path: Path) -> None:
    first = _write_export(tmp_path / "first.json", job_id="job-1")
    second = _write_export(tmp_path / "second.json", job_id="job-2")
    nested = tmp_path / "nested"
    third = _write_export(nested / "third.json", job_id="job-3")

    paths = expand_job_inputs([
        f"{first},{second}",
        str(nested),
        str(tmp_path / "*.json"),
    ])

    assert paths == [first.resolve(), second.resolve(), third.resolve()]


def test_expand_job_inputs_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="job export not found"):
        expand_job_inputs([str(tmp_path / "missing.json")])


def test_load_raw_jobs_from_exports_reads_multiple_files(tmp_path: Path) -> None:
    first = _write_export(tmp_path / "first.json", city="上海", job_id="job-1")
    second = _write_export(tmp_path / "second.json", city="北京", job_id="job-2")

    raw_jobs = load_raw_jobs_from_exports([first, second])

    assert [(job.city, job.source_job_id) for job in raw_jobs] == [("上海", "job-1"), ("北京", "job-2")]


def test_dedupe_normalized_jobs_keeps_last_seen_job() -> None:
    first = _normalized_job("job-1", city="上海")
    second = _normalized_job("job-1", city="北京")
    third = _normalized_job("job-2", city="深圳")

    deduped = dedupe_normalized_jobs([first, second, third])

    assert [(job.source_job_id, job.city) for job in deduped] == [("job-1", "北京"), ("job-2", "深圳")]


def test_analyze_resume_jobs_report_batches_ai_calls() -> None:
    provider = FakeProvider()
    structured_jds = structure_jds([
        _normalized_job("job-1", city="上海"),
        _normalized_job("job-2", city="北京"),
        _normalized_job("job-3", city="深圳"),
    ])

    report = analyze_resume_jobs_report(
        "熟悉 Python 和 RAG。",
        structured_jds,
        provider,
        max_jobs=3,
        batch_size=2,
    )

    assert "# 分批 AI 简历-岗位匹配报告" in report
    assert "批次 1: 岗位 1-2" in report
    assert "批次 2: 岗位 3-3" in report
    assert len(provider.prompts) == 2


def _write_export(path: Path, *, city: str = "上海", job_id: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "keyword": "AI Agent",
                "city": city,
                "jobs": [
                    {
                        "job_id": job_id,
                        "title": "AI 应用工程师",
                        "boss_name": "示例公司",
                        "location": city,
                        "salary": "20-35K",
                        "tags": "1-3年 | 本科",
                        "job_labels": "Python | RAG",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _normalized_job(source_job_id: str, *, city: str) -> NormalizedJobPost:
    return NormalizedJobPost(
        platform="boss_zhipin",
        source_job_id=source_job_id,
        keyword="AI Agent",
        city=city,
        job_title="AI 应用工程师",
        company="示例公司",
        location=city,
        skill_keywords=["Python"],
    )
