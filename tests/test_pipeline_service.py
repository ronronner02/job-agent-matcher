from pathlib import Path

from app.db.session import session_scope
from app.repositories.job_repository import list_jobs
from app.services.pipeline_service import run_offline_job_pipeline


FIXTURE = Path(__file__).parent / "fixtures" / "sample_boss_jobs.json"


def test_run_offline_job_pipeline_persists_and_exports_artifacts(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'job_agent.db'}"
    output_dir = tmp_path / "reports"

    result = run_offline_job_pipeline(
        FIXTURE,
        database_url=database_url,
        output_dir=output_dir,
        top_n=5,
    )

    assert result.raw_job_count == 3
    assert result.normalized_job_count == 3
    assert result.saved_job_count == 3
    assert result.structured_jd_count == 3
    assert result.database_url == database_url
    assert "Python" in result.top_skill_names

    assert result.artifacts.structured_jds_path is not None
    assert result.artifacts.skill_report_path is not None
    assert result.artifacts.markdown_report_path is not None
    assert result.artifacts.structured_jds_path.exists()
    assert result.artifacts.skill_report_path.exists()
    assert result.artifacts.markdown_report_path.exists()
    assert "AI 岗位技能分析报告" in result.artifacts.markdown_report_path.read_text(encoding="utf-8")

    with session_scope(database_url) as session:
        jobs = list_jobs(session)

    assert [job.source_job_id for job in jobs] == [
        "sample-ai-agent-001",
        "sample-rag-002",
        "sample-llm-003",
    ]


def test_run_offline_job_pipeline_can_skip_persistence(tmp_path: Path) -> None:
    result = run_offline_job_pipeline(
        FIXTURE,
        output_dir=tmp_path / "reports",
        persist=False,
    )

    assert result.saved_job_count == 0
    assert result.database_url is None
    assert result.artifacts.skill_report_path is not None
    assert result.artifacts.skill_report_path.exists()
