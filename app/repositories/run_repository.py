from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentRunRecord, AgentStepRecord
from app.schemas.run import AgentRun, AgentStep


def save_agent_run(session: Session, run: AgentRun) -> AgentRunRecord:
    existing = session.get(AgentRunRecord, run.id)
    if existing is None:
        existing = AgentRunRecord(id=run.id)
        session.add(existing)

    existing.task_type = run.task_type
    existing.keyword = run.keyword
    existing.city = run.city
    existing.status = run.status
    existing.total_jobs = run.total_jobs
    existing.success_count = run.success_count
    existing.error_message = run.error_message
    existing.duration_ms = run.duration_ms
    existing.raw_output_path = run.raw_output_path
    existing.command = run.command
    existing.started_at = run.started_at
    existing.finished_at = run.finished_at
    return existing


def save_agent_step(session: Session, step: AgentStep) -> AgentStepRecord:
    existing = session.get(AgentStepRecord, step.id)
    if existing is None:
        existing = AgentStepRecord(id=step.id)
        session.add(existing)

    existing.run_id = step.run_id
    existing.name = step.name
    existing.order_index = step.order_index
    existing.status = step.status
    existing.detail = step.detail
    existing.error_message = step.error_message
    existing.item_count = step.item_count
    existing.duration_ms = step.duration_ms
    existing.artifact_path = step.artifact_path
    existing.started_at = step.started_at
    existing.finished_at = step.finished_at
    return existing


def save_agent_steps(session: Session, steps: list[AgentStep]) -> list[AgentStepRecord]:
    return [save_agent_step(session, step) for step in steps]


def list_agent_steps(session: Session, run_id: str) -> list[AgentStepRecord]:
    stmt = (
        select(AgentStepRecord)
        .where(AgentStepRecord.run_id == run_id)
        .order_by(AgentStepRecord.order_index)
    )
    return list(session.scalars(stmt))
