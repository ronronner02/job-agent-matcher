from pathlib import Path

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.services.job_normalizer import normalize_boss_jobs, split_experience_and_education


FIXTURE = Path(__file__).parent / "fixtures" / "sample_boss_jobs.json"


def test_split_experience_and_education_from_boss_tags() -> None:
    assert split_experience_and_education("3-5年 | 本科") == ("3-5年", "本科")
    assert split_experience_and_education("经验不限 | 硕士") == ("经验不限", "硕士")


def test_normalizer_creates_stable_internal_schema() -> None:
    raw_jobs = BossZhipinCollector(FIXTURE).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)

    first = normalized_jobs[0]
    assert first.platform == "boss_zhipin"
    assert first.source_job_id == "sample-ai-agent-001"
    assert first.keyword == "AI Agent"
    assert first.city == "上海"
    assert first.job_title == "AI Agent 应用工程师"
    assert first.company == "示例智能科技"
    assert first.experience_required == "3-5年"
    assert first.education_required == "本科"
    assert first.skill_keywords == ["Python", "FastAPI", "LangGraph", "RAG"]
    assert "负责 AI Agent 应用开发" in (first.jd_text or "")


def test_normalizer_promotes_company_and_job_metadata() -> None:
    raw_jobs = BossZhipinCollector(FIXTURE).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)

    first = normalized_jobs[0]
    assert first.company_scale == "100-499人"
    assert first.company_stage == "B轮"
    assert first.company_industry == "人工智能"
    assert first.company_link == "https://www.zhipin.com/gongsi/sample-ai-agent-001.html"
    assert first.address == "上海市浦东新区张江高科技园区博云路 2 号"
    assert first.boss_title == "技术负责人"
    assert first.job_url == "https://www.zhipin.com/job_detail/sample-ai-agent-001.html"
    assert first.welfare == ["五险一金", "补充医疗保险", "股票期权", "弹性工作"]


def test_normalizer_parses_salary_into_min_max_unit() -> None:
    raw_jobs = BossZhipinCollector(FIXTURE).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)

    first = normalized_jobs[0]
    assert first.salary == "25-45K·14薪"
    assert first.salary_min == 25000
    assert first.salary_max == 45000
    assert first.salary_unit == "month"
