from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DATABASE_URL = "sqlite:///data/db/job_agent.db"
DEFAULT_RAW_OUTPUT_DIR = "data/raw_jobs"
DEFAULT_REPORT_DIR = "data/reports"
DEFAULT_RUN_LOG_PATH = "data/runs/agent_runs.jsonl"
DEFAULT_CDP_PORT = 9222


@dataclass(frozen=True)
class Settings:
    """Central place for environment-driven configuration.

    Individual services still accept explicit overrides in their constructors
    (which keeps them easy to test); this type just collects the process-wide
    defaults so the FastAPI layer added later has one obvious import instead of
    scattered ``os.environ`` reads.
    """

    database_url: str = DEFAULT_DATABASE_URL
    scraper_root: str | None = None
    raw_output_dir: str = DEFAULT_RAW_OUTPUT_DIR
    report_dir: str = DEFAULT_REPORT_DIR
    run_log_path: str = DEFAULT_RUN_LOG_PATH
    cdp_port: int = DEFAULT_CDP_PORT

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("JOB_AGENT_DATABASE_URL", DEFAULT_DATABASE_URL),
            scraper_root=os.environ.get("BOSS_SCRAPER_ROOT"),
            raw_output_dir=os.environ.get("BOSS_RAW_OUTPUT_DIR", DEFAULT_RAW_OUTPUT_DIR),
            report_dir=os.environ.get("JOB_AGENT_REPORT_DIR", DEFAULT_REPORT_DIR),
            run_log_path=os.environ.get("BOSS_RUN_LOG_PATH", DEFAULT_RUN_LOG_PATH),
            cdp_port=_int_env("BOSS_CDP_PORT", DEFAULT_CDP_PORT),
        )

    @property
    def report_path(self) -> Path:
        return Path(self.report_dir)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_settings() -> Settings:
    return Settings.from_env()
