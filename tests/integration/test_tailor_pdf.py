import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from shortlist.tailor.pdf import PandocMissingError, render_md_to_pdf

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _pdflatex_functional() -> bool:
    """Return True only if pdflatex can actually produce a PDF (format file present)."""
    if not (_have("pandoc") and _have("pdflatex")):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "probe.md"
        md.write_text("hello")
        result = subprocess.run(
            ["pandoc", str(md), "-o", str(Path(tmp) / "probe.pdf"), "--pdf-engine=pdflatex"],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0


@pytest.mark.skipif(not _pdflatex_functional(), reason="pandoc + functional pdflatex required")
def test_render_md_to_pdf_writes_pdf(tmp_path: Path):
    md = tmp_path / "in.md"
    md.write_text("# Hello\n\nThis is a test.\n")
    pdf = tmp_path / "out.pdf"
    render_md_to_pdf(md, pdf, template=FIXTURES / "pdf-template.tex")
    assert pdf.exists()
    assert pdf.stat().st_size > 0


def test_render_md_to_pdf_raises_when_pandoc_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _c: None)
    md = tmp_path / "in.md"
    md.write_text("# x")
    pdf = tmp_path / "out.pdf"
    with pytest.raises(PandocMissingError):
        render_md_to_pdf(md, pdf)
