from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from statistics import mean
from typing import Any


# These are list-page fields that should be available before fetching optional
# detail pages. JD text is intentionally excluded because --no-detail is a
# supported, fast collection mode.
DEFAULT_REQUIRED_FIELDS = (
    "source_job_id",
    "title",
    "company",
    "location",
    "salary",
    "tags",
    "job_url",
)


def field_completeness(
    jobs: Sequence[Mapping[str, Any]],
    *,
    fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
) -> float:
    """Return the ratio of non-empty required raw-job fields."""

    if not jobs or not fields:
        return 0.0
    present = sum(
        1
        for job in jobs
        for field in fields
        if _is_present(job.get(field))
    )
    return round(present / (len(jobs) * len(fields)), 4)


def collection_success_rate(runs: Iterable[Mapping[str, Any]]) -> float | None:
    """Return successful collection tasks divided by all collection tasks."""

    collection_runs = [run for run in runs if run.get("task_type") == "boss_collect"]
    if not collection_runs:
        return None
    successful = sum(1 for run in collection_runs if run.get("status") == "success")
    return round(successful / len(collection_runs), 4)


def average_task_latency_seconds(runs: Iterable[Mapping[str, Any]]) -> float | None:
    """Return the mean duration of collection tasks with a valid duration."""

    durations = [
        float(run["duration_ms"]) / 1000
        for run in runs
        if run.get("task_type") == "boss_collect"
        and isinstance(run.get("duration_ms"), (int, float))
        and run["duration_ms"] >= 0
    ]
    if not durations:
        return None
    return round(mean(durations), 3)


def skill_tag_scores(
    predicted: Mapping[str, Sequence[str]],
    gold: Mapping[str, Sequence[str]],
) -> dict[str, float | int | None]:
    """Score predicted skills against independent per-job reference tags.

    ``accuracy`` is micro-F1, which balances missed tags and extra tags. The
    name is kept for compatibility with the resume metric requested in the
    learning plan; precision and recall are emitted so the number is clear.
    """

    if not gold:
        return {"accuracy": None, "precision": None, "recall": None, "gold_jobs": 0}

    true_positive = false_positive = false_negative = 0
    for job_id, expected_values in gold.items():
        expected = {_normalise_skill(value) for value in expected_values if _is_present(value)}
        actual = {
            _normalise_skill(value)
            for value in predicted.get(job_id, [])
            if _is_present(value)
        }
        true_positive += len(expected & actual)
        false_positive += len(actual - expected)
        false_negative += len(expected - actual)

    precision = _safe_ratio(true_positive, true_positive + false_positive)
    recall = _safe_ratio(true_positive, true_positive + false_negative)
    f1 = (
        round(2 * precision * recall / (precision + recall), 4)
        if precision is not None and recall is not None and precision + recall
        else 0.0
    )
    return {
        "accuracy": f1,
        "precision": precision,
        "recall": recall,
        "gold_jobs": len(gold),
    }


def match_explanation_validity(
    results: Sequence[Mapping[str, Any]],
    expected_job_ids: set[str],
) -> float | None:
    """Check result coverage and required explanation fields.

    This is a structural validity metric, not a claim that the model's prose
    is semantically correct. A human or LLM judge is needed for that stronger
    claim.
    """

    if not results or not expected_job_ids:
        return None
    by_id = {str(item.get("source_job_id")): item for item in results}
    valid = 0
    for job_id in expected_job_ids:
        item = by_id.get(job_id)
        if item and job_id in expected_job_ids and all(
            _non_empty_string_list(item.get(field))
            for field in ("matched_evidence", "gaps", "resume_suggestions", "interview_focus")
        ):
            valid += 1
    return round(valid / len(expected_job_ids), 4)


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _non_empty_string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _normalise_skill(value: Any) -> str:
    return " ".join(str(value).strip().lower().split())


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None
