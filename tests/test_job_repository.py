from pathlib import Path

from sqlalchemy import select

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.db.models import AgentRunRecord, JobPost, JobSkill
from app.db.session import session_scope
from app.schemas.run import AgentRun
from app.services.job_normalizer import normalize_boss_jobs
from app.repositories.job_repository import list_jobs, upsert_normalized_jobs
from app.repositories.run_repository import save_agent_run


FIXTURE = Path(__file__).parent / "fixtures" / "sample_boss_jobs.json"


def test_upsert_normalized_jobs_persists_posts_and_skills(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'job_agent.db'}"
    raw_jobs = BossZhipinCollector(FIXTURE).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)

    with session_scope(database_url) as session:
        saved = upsert_normalized_jobs(session, normalized_jobs)

    assert len(saved) == 3

    with session_scope(database_url) as session:
        jobs = list_jobs(session, keyword="AI Agent", city="上海")
        skills = list(session.scalars(select(JobSkill.skill).order_by(JobSkill.skill)))

    assert [job.source_job_id for job in jobs] == [
        "sample-ai-agent-001",
        "sample-rag-002",
        "sample-llm-003",
    ]
    assert "FastAPI" in skills
    assert "LangGraph" in skills
    assert "向量数据库" in skills


def test_upsert_normalized_jobs_updates_existing_job_without_duplicates(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'job_agent.db'}"
    raw_jobs = BossZhipinCollector(FIXTURE).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)
    normalized_jobs[0] = normalized_jobs[0].model_copy(update={"salary": "28-50K"})

    with session_scope(database_url) as session:
        upsert_normalized_jobs(session, normalized_jobs)
        upsert_normalized_jobs(session, normalized_jobs)

    with session_scope(database_url) as session:
        posts = list(session.scalars(select(JobPost)))
        first = session.scalar(
            select(JobPost).where(JobPost.source_job_id == "sample-ai-agent-001")
        )

    assert len(posts) == 3
    assert first is not None
    assert first.salary == "28-50K"


def test_upsert_persists_company_and_job_metadata(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'job_agent.db'}"
    raw_jobs = BossZhipinCollector(FIXTURE).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)

    with session_scope(database_url) as session:
        upsert_normalized_jobs(session, normalized_jobs)

    with session_scope(database_url) as session:
        first = session.scalar(
            select(JobPost).where(JobPost.source_job_id == "sample-ai-agent-001")
        )

    assert first is not None
    assert first.company_scale == "100-499人"
    assert first.company_stage == "B轮"
    assert first.company_industry == "人工智能"
    assert first.company_link == "https://www.zhipin.com/gongsi/sample-ai-agent-001.html"
    assert first.address == "上海市浦东新区张江高科技园区博云路 2 号"
    assert first.job_url == "https://www.zhipin.com/job_detail/sample-ai-agent-001.html"
    assert first.salary_min == 25000
    assert first.salary_max == 45000
    assert first.welfare == ["五险一金", "补充医疗保险", "股票期权", "弹性工作"]


def test_save_agent_run_persists_execution_trace(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'job_agent.db'}"
    run = AgentRun(
        task_type="boss_collect",
        keyword="AI Agent",
        city="上海",
        status="success",
        total_jobs=3,
        success_count=3,
        duration_ms=1200,
        raw_output_path="data/raw_jobs/sample.json",
        command=["python", "boss_cdp_raw.py"],
    )

    with session_scope(database_url) as session:
        save_agent_run(session, run)

    with session_scope(database_url) as session:
        saved = session.get(AgentRunRecord, run.id)

    assert saved is not None
    assert saved.status == "success"
    assert saved.total_jobs == 3
    assert saved.command == ["python", "boss_cdp_raw.py"]
