from pathlib import Path

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.services.jd_structurer import split_sentences, structure_jd, structure_jds
from app.services.job_normalizer import normalize_boss_jobs


FIXTURE = Path(__file__).parent / "fixtures" / "sample_boss_jobs.json"


def _normalized_jobs():
    return normalize_boss_jobs(BossZhipinCollector(FIXTURE).collect())


def test_split_sentences_handles_chinese_punctuation() -> None:
    assert split_sentences("负责开发。熟悉 Python；具备 RAG 经验") == [
        "负责开发",
        "熟悉 Python",
        "具备 RAG 经验",
    ]


def test_structure_jd_extracts_skills_and_responsibilities() -> None:
    structured = structure_jd(_normalized_jobs()[0])

    skill_names = [skill.name for skill in structured.skills]
    assert structured.source_job_id == "sample-ai-agent-001"
    assert structured.job_title == "AI Agent 应用工程师"
    assert "AI Agent" in skill_names
    assert "FastAPI" in skill_names
    assert "RAG" in skill_names
    assert structured.responsibilities
    assert structured.requirements == ["经验要求：3-5年", "学历要求：本科"]
    assert structured.confidence >= 0.8
    assert "大模型应用" in " ".join(structured.risk_points)


def test_structure_jd_extracts_data_and_devops_skills() -> None:
    structured = structure_jd(_normalized_jobs()[1])
    skills = {skill.name: skill.category for skill in structured.skills}

    assert skills["SQL"] == "data"
    assert skills["Docker"] == "devops"
    assert skills["向量数据库"] == "data"
    assert any("性能" in risk for risk in structured.risk_points)


def test_structure_jds_batch_keeps_one_result_per_job() -> None:
    structured = structure_jds(_normalized_jobs())

    assert len(structured) == 3
    assert [item.source_job_id for item in structured] == [
        "sample-ai-agent-001",
        "sample-rag-002",
        "sample-llm-003",
    ]
    assert all(item.summary for item in structured)
