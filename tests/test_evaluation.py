from app.services.evaluation import (
    average_task_latency_seconds,
    collection_success_rate,
    field_completeness,
    match_explanation_validity,
    skill_tag_scores,
)
from scripts.evaluate_job_agent import select_runs_for_exports


def test_field_completeness_counts_non_empty_required_fields() -> None:
    jobs = [{"title": "A", "company": "C"}, {"title": "B", "company": ""}]
    assert field_completeness(jobs, fields=("title", "company")) == 0.75


def test_collection_rate_and_average_latency_use_collection_runs_only() -> None:
    runs = [
        {"task_type": "boss_collect", "status": "success", "duration_ms": 1000},
        {"task_type": "boss_collect", "status": "failed", "duration_ms": 3000},
        {"task_type": "other", "status": "success", "duration_ms": 9999},
    ]
    assert collection_success_rate(runs) == 0.5
    assert average_task_latency_seconds(runs) == 2.0


def test_skill_scores_are_micro_f1_against_gold_labels() -> None:
    scores = skill_tag_scores(
        {"a": ["Python", "RAG"], "b": ["SQL"]},
        {"a": ["Python"], "b": ["Docker"]},
    )
    assert scores["precision"] == 0.3333
    assert scores["recall"] == 0.5
    assert scores["accuracy"] == 0.4


def test_match_validity_requires_coverage_and_explanation_fields() -> None:
    result = {
        "source_job_id": "a",
        "matched_evidence": ["Python"],
        "gaps": ["Docker"],
        "resume_suggestions": ["补充项目指标"],
        "interview_focus": ["解释系统设计"],
    }
    assert match_explanation_validity([result], {"a", "b"}) == 0.5


def test_run_log_is_scoped_to_the_evaluated_export() -> None:
    runs = [
        {"raw_output_path": "data/raw_jobs/old.json", "task_type": "boss_collect"},
        {"raw_output_path": "data/raw_jobs/current.json", "task_type": "boss_collect"},
    ]
    selected = select_runs_for_exports(runs, ["data/raw_jobs/current.json"])
    assert selected == [runs[1]]
