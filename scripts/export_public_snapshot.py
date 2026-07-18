from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Directories whose whole tree is safe to publish (source + tests only).
ALLOWED_DIRS = ("app", "scripts", "tests")

# Individual files that must be published verbatim.
ALLOWED_FILES = (
    "README.md",
    "pyproject.toml",
    ".env.example",
    ".gitignore",
    "external/README.md",
)

# Public technical documentation is explicit rather than directory-wide so
# personal notes can never enter the snapshot.
ALLOWED_DOCS = (
    "docs/evaluation.md",
    "docs/design-decisions/ai-resume-job-analysis.md",
    "docs/design-decisions/cdp-profile-and-safety.md",
    "docs/design-decisions/collector-adapter.md",
    "docs/design-decisions/compliance.md",
    "docs/design-decisions/database-modeling.md",
    "docs/design-decisions/jd-structuring.md",
    "docs/design-decisions/job-agent-workflow.md",
    "docs/design-decisions/pipeline-flow.md",
    "docs/design-decisions/project-boundary.md",
    "docs/design-decisions/skill-analyzer.md",
)

# Placeholder-only files: we copy the empty directory markers so the public
# snapshot keeps the runtime layout without any real data.
ALLOWED_GITKEEPS = (
    "data/raw_jobs/.gitkeep",
    "data/reports/.gitkeep",
    "data/runs/.gitkeep",
    "data/db/.gitkeep",
    "data/processed_jobs/.gitkeep",
    "private/.gitkeep",
)

# Anything matching these path parts is NEVER copied, even from allowed dirs.
DENY_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
}

# File suffixes that must never leave the machine (secrets, real data, caches).
DENY_SUFFIXES = {".env", ".pyc", ".db", ".db-shm", ".db-wal", ".log", ".pdf", ".docx"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a clean, publishable snapshot (source only, no secrets or real data).",
    )
    parser.add_argument("--dest", required=True, help="Destination directory for the snapshot.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination directory if it already exists.",
    )
    args = parser.parse_args()

    dest = Path(args.dest).resolve()
    if dest == PROJECT_ROOT or PROJECT_ROOT in dest.parents:
        print("ERROR: --dest must be outside the project directory.", file=sys.stderr)
        return 2
    if dest.exists():
        if not args.force:
            print(f"ERROR: {dest} already exists (use --force to overwrite).", file=sys.stderr)
            return 2
        shutil.rmtree(dest)

    copied = _export(PROJECT_ROOT, dest)
    print(f"Exported {copied} files to {dest}")
    return 0


def _export(root: Path, dest: Path) -> int:
    copied = 0

    for rel in (*ALLOWED_FILES, *ALLOWED_DOCS):
        src = root / rel
        if src.is_file():
            copied += _copy_file(src, dest / rel)

    for rel in ALLOWED_GITKEEPS:
        src = root / rel
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            copied += _copy_file(src, target)
        else:
            # Directory exists but the marker is missing: still create the dir.
            target.write_text("", encoding="utf-8")
            copied += 1

    for dir_name in ALLOWED_DIRS:
        src_dir = root / dir_name
        if not src_dir.is_dir():
            continue
        for src in src_dir.rglob("*"):
            if not src.is_file():
                continue
            if _is_denied(src):
                continue
            copied += _copy_file(src, dest / src.relative_to(root))

    return copied


def _is_denied(path: Path) -> bool:
    if any(part in DENY_PARTS for part in path.parts):
        return True
    # ``.env`` has no suffix under Path.suffix, so match the name too.
    if path.name == ".env" or path.name.startswith(".env."):
        return path.name != ".env.example"
    return path.suffix.lower() in DENY_SUFFIXES


def _copy_file(src: Path, target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
