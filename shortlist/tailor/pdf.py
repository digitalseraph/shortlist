"""Pandoc subprocess wrapper.

If pandoc or pdflatex is missing on PATH, raise PandocMissingError. Callers
treat that as a soft failure — MD outputs are still useful.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class PandocMissingError(RuntimeError):
    pass


class PandocRenderError(RuntimeError):
    pass


def _check_tools() -> None:
    if not shutil.which("pandoc"):
        raise PandocMissingError("pandoc not found on PATH")
    if not shutil.which("pdflatex"):
        raise PandocMissingError("pdflatex not found on PATH (install texlive-core)")


def render_md_to_pdf(
    md_path: Path,
    pdf_path: Path,
    *,
    template: Path | None = None,
) -> None:
    _check_tools()
    cmd = ["pandoc", str(md_path), "-o", str(pdf_path), "--pdf-engine=pdflatex"]
    if template is not None:
        cmd.extend(["--template", str(template)])
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
    except subprocess.CalledProcessError as e:
        raise PandocRenderError(f"pandoc failed: {e.stderr.strip()}") from e
