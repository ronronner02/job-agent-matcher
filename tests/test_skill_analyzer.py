from pathlib import Path

from app.collectors.boss_zhipin_collector import BossZhipinCollector
from app.services.jd_structurer import structure_jds
from app.services.job_normalizer import normalize_boss_jobs
from app.services.skill_analyzer import analyze_skills, build_skill_summary


FIXTURE = Path(__file__).parent / "fixtures" / "sample_boss_jobs.json"


def _structured_jds():
    raw_jobs = BossZhipinCollector(FIXTURE).collect()
    normalized_jobs = normalize_boss_jobs(raw_jobs)
    return structure_jds(normalized_jobs)


def test_analyze_skills_counts_top_skills_and_coverage() -> None:
    report = analyze_skills(_structured_jds(), top_n=5)

    top_by_name = {skill.name: skill for skill in report.top_skills}
    assert report.total_jobs == 3
    assert top_by_name["Python"].job_count == 3
    assert top_by_name["Python"].coverage == 1.0
    assert top_by_name["RAG"].job_count == 2
    assert report.required_skill_names[0] == "Python"
    assert "Python" in report.summary


def test_analyze_skills_groups_categories() -> None:
    report = analyze_skills(_structured_jds())
    categories = {item.category: item for item in report.category_distribution}

    assert categories["ai"].coverage == 1.0
    assert categories["data"].coverage >= 0.66
    assert categories["backend"].mention_count >= 2
    assert any("RAG/Agent/LLM" in item for item in report.recommendations)


def test_analyze_skills_finds_common_pairs() -> None:
    report = analyze_skills(_structured_jds(), pair_top_n=100)
    pair_counts = {tuple(pair.skills): pair.count for pair in report.common_skill_pairs}

    assert pair_counts[("Python", "RAG")] == 2
    assert ("Docker", "Python") in pair_counts


def test_analyze_skills_handles_empty_input() -> None:
    report = analyze_skills([])

    assert report.total_jobs == 0
    assert report.top_skills == []
    assert report.category_distribution == []
    assert report.summary == "暂无岗位数据，无法生成技能画像。"
    assert build_skill_summary(0, [], []) == report.summary
