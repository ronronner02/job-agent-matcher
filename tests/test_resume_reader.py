from pathlib import Path

import pytest

from app.services.resume_reader import read_resume_text


def test_read_resume_text_reads_txt(tmp_path: Path) -> None:
    resume = tmp_path / "resume.txt"
    resume.write_text("Python RAG FastAPI", encoding="utf-8")

    assert read_resume_text(resume) == "Python RAG FastAPI"


def test_read_resume_text_reads_pdf(tmp_path: Path) -> None:
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    resume = tmp_path / "resume.pdf"
    pdf = canvas.Canvas(str(resume))
    pdf.drawString(72, 720, "Python RAG FastAPI resume")
    pdf.save()

    assert "Python RAG FastAPI" in read_resume_text(resume)


def test_read_resume_text_rejects_unsupported_file(tmp_path: Path) -> None:
    resume = tmp_path / "resume.docx"
    resume.write_text("content", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported resume file type"):
        read_resume_text(resume)
