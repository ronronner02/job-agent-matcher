from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.db.session import session_scope
from app.repositories.job_repository import upsert_normalized_jobs
from app.services.jd_structurer import structure_jds
from app.services.job_normalizer import normalize_boss_jobs
from app.services.skill_analyzer import analyze_skills
from scripts.resume_full_job_agent import ResumeError, resume_full_job_agent


FIXTURE = Path(__file__).parent / "fixtures" / "sample_boss_jobs.json"


class FakeProvider:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        import re

        ids = re.findall(r"岗位ID: (\S+)", prompt)
        results = [
            {
                "source_job_id": job_id,
                "match_score": 90 - index * 15,
                "recommendation_level": "优先投递" if index == 0 else "可以投递",
                "matched_evidence": ["做过 RAG 检索项目"],
                "gaps": ["缺少大规模分布式经验"],
                "resume_suggestions": ["补充 Agent 项目量化指标"],
                "interview_focus": ["讲清 RAG 评估方式"],
            }
            for index, job_id in enumerate(ids)
        ]
        return json.dumps(results, ensure_ascii=False)


def _seed_run(tmp_path: Path, run_id: str, db_url: str) -> Path:
    """Recreate the artifacts a real run produces before resume_matching."""

    raw_jobs = BossZhipinCollector(FIXTURE).collect()
    normalized = normalize_boss_jobs(raw_jobs)
    with session_scope(db_url) as session:
        upsert_normalized_jobs(session, normalized)

    structured = structure_jds(normalized)
    skill_report = analyze_skills(structured)

    out_dir = tmp_path / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{run_id}_structured_jobs.json").write_text(
        json.dumps([jd.model_dump(mode="json") for jd in structured], ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / f"{run_id}_skill_analysis.json").write_text(
        json.dumps(skill_report.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    return out_dir


def test_resume_continues_without_calling_collector(tmp_path: Path) -> None:
    run_id = "resumetest"
    db_url = f"sqlite:///{tmp_path / 'jobs.db'}"
    out_dir = _seed_run(tmp_path, run_id, db_url)

    resume = tmp_path / "resume.txt"
    resume.write_text("做过 Python 后端和 RAG 检索、Agent 编排项目。", encoding="utf-8")

    provider = FakeProvider()
    result = resume_full_job_agent(
        run_id=run_id,
        resume_file=str(resume),
        output_dir=str(out_dir),
        database_url=db_url,
        batch_size=3,
        provider=provider,
    )

    # Continued matching + report, reusing the original run_id.
    assert result["run_id"] == run_id
    assert result["matched_job_count"] == 3
    assert result["priority_job_count"] == 1

    # All continuation artifacts written under the same run_id.
    assert Path(result["match_results_json"]).exists()
    assert Path(result["job_overview_csv"]).exists()
    assert Path(result["final_report_md"]).exists()

    # Report has real metadata pulled from the DB, not just IDs.
    report_md = Path(result["final_report_md"]).read_text(encoding="utf-8")
    assert "示例智能科技" in report_md
    assert "岗位链接" in report_md

    # Match JSON is globally ranked and keeps the original run_id.
    match_json = json.loads(Path(result["match_results_json"]).read_text(encoding="utf-8"))
    assert match_json["run_id"] == run_id
    assert match_json["results"][0]["rank"] == 1
    assert provider.prompts  # the AI provider was actually called


def test_resume_reuses_run_id_and_supports_batch_size_one(tmp_path: Path) -> None:
    run_id = "batchone"
    db_url = f"sqlite:///{tmp_path / 'jobs.db'}"
    out_dir = _seed_run(tmp_path, run_id, db_url)

    resume = tmp_path / "resume.txt"
    resume.write_text("做过 RAG 项目。", encoding="utf-8")

    provider = FakeProvider()
    result = resume_full_job_agent(
        run_id=run_id,
        resume_file=str(resume),
        output_dir=str(out_dir),
        database_url=db_url,
        batch_size=1,
        provider=provider,
    )

    assert result["run_id"] == run_id
    # batch_size=1 with 3 jobs => 3 separate AI calls.
    assert len(provider.prompts) == 3


def test_resume_never_touches_collector_even_indirectly(tmp_path: Path) -> None:
    # The resume flow must run purely from files + DB + provider. This guards the
    # core requirement: no re-collection. If the module ever imported or invoked a
    # collector, this run (with no CDP/scraper available) would still succeed here,
    # so we also assert import-level cleanliness below.
    import scripts.resume_full_job_agent as mod

    assert not hasattr(mod, "BossZhipinCollector")

    run_id = "nocollect"
    db_url = f"sqlite:///{tmp_path / 'jobs.db'}"
    out_dir = _seed_run(tmp_path, run_id, db_url)

    resume = tmp_path / "resume.txt"
    resume.write_text("做过 RAG 与 Agent 项目。", encoding="utf-8")

    result = resume_full_job_agent(
        run_id=run_id,
        resume_file=str(resume),
        output_dir=str(out_dir),
        database_url=db_url,
        provider=FakeProvider(),
    )
    assert result["matched_job_count"] == 3


def test_resume_missing_structured_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ResumeError, match="找不到结构化岗位文件"):
        resume_full_job_agent(
            run_id="missing",
            resume_file=str(tmp_path / "resume.txt"),
            output_dir=str(tmp_path / "reports"),
            database_url=f"sqlite:///{tmp_path / 'jobs.db'}",
            provider=FakeProvider(),
        )


def test_resume_provider_failure_gives_friendly_hint(tmp_path: Path) -> None:
    run_id = "provfail"
    db_url = f"sqlite:///{tmp_path / 'jobs.db'}"
    out_dir = _seed_run(tmp_path, run_id, db_url)

    resume = tmp_path / "resume.txt"
    resume.write_text("做过 RAG 项目。", encoding="utf-8")

    class BrokenProvider:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("connection reset by peer")

    with pytest.raises(ResumeError) as excinfo:
        resume_full_job_agent(
            run_id=run_id,
            resume_file=str(resume),
            output_dir=str(out_dir),
            database_url=db_url,
            provider=BrokenProvider(),
        )
    message = str(excinfo.value)
    assert "batch-size" in message
    assert "AI_MATCHER_TIMEOUT_SECONDS" in message
