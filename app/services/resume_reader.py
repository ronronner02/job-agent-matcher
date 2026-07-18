from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


SUPPORTED_RESUME_EXTENSIONS = {".pdf", ".txt", ".md"}


def read_resume_text(path: str | Path) -> str:
    """Read private resume text from PDF, TXT, or Markdown files."""

    resume_path = Path(path)
    suffix = resume_path.suffix.lower()
    if suffix not in SUPPORTED_RESUME_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_RESUME_EXTENSIONS))
        raise ValueError(f"unsupported resume file type: {suffix or '<none>'}; supported: {supported}")

    if suffix == ".pdf":
        text = _read_pdf_text(resume_path)
    else:
        text = resume_path.read_text(encoding="utf-8")

    cleaned = text.strip()
    if not cleaned:
        raise ValueError(f"resume file contains no extractable text: {resume_path}")
    return cleaned


def _read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(page.strip() for page in pages if page.strip())
