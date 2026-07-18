from __future__ import annotations

from typing import Protocol

from app.schemas.job import RawJobPost


class JobCollector(Protocol):
    """Common collector contract for current and future job platforms."""

    def collect(self) -> list[RawJobPost]:
        """Return raw jobs in the project's internal raw schema."""
