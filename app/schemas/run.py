from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


RunStatus = Literal["pending", "running", "success", "failed"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentRun(BaseModel):
    """Execution trace for one agent task."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex)
    task_type: str
    keyword: str | None = None
    city: str | None = None
    status: RunStatus = "pending"
    total_jobs: int = 0
    success_count: int = 0
    error_message: str | None = None
    duration_ms: int | None = None
    raw_output_path: str | None = None
    command: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    def finish_success(self, *, total_jobs: int, duration_ms: int) -> AgentRun:
        return self.model_copy(
            update={
                "status": "success",
                "total_jobs": total_jobs,
                "success_count": total_jobs,
                "duration_ms": duration_ms,
                "finished_at": utc_now(),
            }
        )

    def finish_failed(self, *, error_message: str, duration_ms: int) -> AgentRun:
        return self.model_copy(
            update={
                "status": "failed",
                "error_message": error_message,
                "duration_ms": duration_ms,
                "finished_at": utc_now(),
            }
        )


class AgentStep(BaseModel):
    """One step within a multi-step workflow run.

    Steps let a full-pipeline run report exactly which stage failed (collect,
    normalize, structure, match, report, ...) rather than a single opaque
    success/failure for the whole thing.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex)
    run_id: str
    name: str
    order_index: int = 0
    status: RunStatus = "pending"
    detail: str | None = None
    error_message: str | None = None
    item_count: int | None = None
    duration_ms: int | None = None
    artifact_path: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    def finish_success(
        self,
        *,
        detail: str | None = None,
        item_count: int | None = None,
        duration_ms: int | None = None,
        artifact_path: str | None = None,
    ) -> AgentStep:
        return self.model_copy(
            update={
                "status": "success",
                "detail": detail,
                "item_count": item_count,
                "duration_ms": duration_ms,
                "artifact_path": artifact_path,
                "finished_at": utc_now(),
            }
        )

    def finish_failed(
        self,
        *,
        error_message: str,
        duration_ms: int | None = None,
    ) -> AgentStep:
        return self.model_copy(
            update={
                "status": "failed",
                "error_message": error_message,
                "duration_ms": duration_ms,
                "finished_at": utc_now(),
            }
        )
