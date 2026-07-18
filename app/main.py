"""Application entrypoint.

The project's real entrypoint today is the CLI in ``scripts/run_full_job_agent.py``,
which drives ``app.services.job_agent_workflow.run_full_job_agent_workflow``.

This module is kept as a thin, dependency-light boundary so a FastAPI (or other
service) layer can be added later without reshuffling the package: routes would
live under ``app/api`` and call the same workflow/service functions that the CLI
already uses. Configuration is centralized in ``app.core.config``.
"""

from __future__ import annotations


def main() -> int:
    print(
        "job-agent-matcher\n"
        "Run the full pipeline with:\n"
        "  python scripts/run_full_job_agent.py --resume-file <path> --keyword <kw> "
        "--cities 上海,深圳 --scraper-root external/boss-zhipin-scraper\n"
        "See README.md for the architecture and compliance boundary."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
