from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import JobMatchRecord
from app.schemas.match import JobMatchReport, JobMatchResult


def save_match_report(session: Session, report: JobMatchReport) -> list[JobMatchRecord]:
    """Persist all match results for a run, replacing any prior run results."""

    session.query(JobMatchRecord).filter(JobMatchRecord.run_id == report.run_id).delete()
    session.flush()

    saved: list[JobMatchRecord] = []
    for result in report.results:
        record = _to_record(report.run_id, result)
        session.add(record)
        saved.append(record)
    session.flush()
    return saved


def list_match_results(session: Session, run_id: str) -> list[JobMatchRecord]:
    stmt = (
        select(JobMatchRecord)
        .where(JobMatchRecord.run_id == run_id)
        .order_by(JobMatchRecord.rank)
    )
    return list(session.scalars(stmt))


def _to_record(run_id: str, result: JobMatchResult) -> JobMatchRecord:
    return JobMatchRecord(
        run_id=run_id,
        source_job_id=result.source_job_id,
        rank=result.rank,
        match_score=result.match_score,
        recommendation_level=result.recommendation_level,
        matched_evidence=list(result.matched_evidence),
        gaps=list(result.gaps),
        resume_suggestions=list(result.resume_suggestions),
        interview_focus=list(result.interview_focus),
    )
