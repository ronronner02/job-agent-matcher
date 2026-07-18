from __future__ import annotations

from pathlib import Path

from scripts.export_public_snapshot import _export, _is_denied


def _touch(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fake_project(root: Path) -> None:
    # Allowed source.
    _touch(root / "app" / "main.py", "print('hi')")
    _touch(root / "scripts" / "run.py", "print('run')")
    _touch(root / "tests" / "test_x.py", "def test_x(): pass")
    _touch(root / "README.md", "# readme")
    _touch(root / "pyproject.toml", "[project]")
    _touch(root / ".env.example", "KEY=")
    _touch(root / ".gitignore", ".env")
    _touch(root / "external" / "README.md", "external")
    _touch(root / "docs" / "evaluation.md", "evaluation")
    _touch(root / "docs" / "design-decisions" / "compliance.md", "compliance")
    _touch(root / "docs" / "source-reading" / "private-notes.md", "private notes")
    _touch(root / "data" / "raw_jobs" / ".gitkeep", "")
    _touch(root / "private" / ".gitkeep", "")

    # Must NEVER be exported.
    _touch(root / ".env", "SECRET=real")
    _touch(root / "private" / "private_resume.pdf", "resume")
    _touch(root / "data" / "raw_jobs" / "boss_jobs_real.json", "{}")
    _touch(root / "data" / "reports" / "run_final_report.md", "report")
    _touch(root / "data" / "db" / "job_agent.db", "sqlite")
    _touch(root / "docs" / "daily" / "day-01.md", "learning notes")
    _touch(root / "docs" / "private-qa" / "preparation.md", "private notes")
    _touch(root / "app" / "__pycache__" / "main.cpython-312.pyc", "bytecode")
    _touch(root / "external" / "boss-zhipin-scraper" / "scripts" / "boss_cdp_raw.py", "scraper")


def test_export_includes_only_allowlisted_content(tmp_path: Path) -> None:
    root = tmp_path / "project"
    dest = tmp_path / "snapshot"
    _fake_project(root)

    _export(root, dest)

    # Allowed content present.
    assert (dest / "app" / "main.py").exists()
    assert (dest / "scripts" / "run.py").exists()
    assert (dest / "tests" / "test_x.py").exists()
    assert (dest / "README.md").exists()
    assert (dest / "pyproject.toml").exists()
    assert (dest / ".env.example").exists()
    assert (dest / ".gitignore").exists()
    assert (dest / "external" / "README.md").exists()
    assert (dest / "docs" / "evaluation.md").exists()
    assert (dest / "docs" / "design-decisions" / "compliance.md").exists()
    assert (dest / "data" / "raw_jobs" / ".gitkeep").exists()
    assert (dest / "private" / ".gitkeep").exists()

    # Forbidden content absent.
    assert not (dest / ".env").exists()
    assert not (dest / "private" / "private_resume.pdf").exists()
    assert not (dest / "data" / "raw_jobs" / "boss_jobs_real.json").exists()
    assert not (dest / "data" / "reports" / "run_final_report.md").exists()
    assert not (dest / "data" / "db" / "job_agent.db").exists()
    assert not (dest / "docs" / "daily").exists()
    assert not (dest / "docs" / "private-qa").exists()
    assert not (dest / "docs" / "source-reading").exists()
    assert not (dest / "app" / "__pycache__").exists()
    # The external scraper source must never be exported.
    assert not (dest / "external" / "boss-zhipin-scraper").exists()


def test_is_denied_blocks_secrets_and_data() -> None:
    assert _is_denied(Path("app/__pycache__/x.pyc"))
    assert _is_denied(Path(".env"))
    assert _is_denied(Path("data/db/job_agent.db"))
    assert _is_denied(Path("private/resume.pdf"))
    assert not _is_denied(Path(".env.example"))
    assert not _is_denied(Path("app/main.py"))
