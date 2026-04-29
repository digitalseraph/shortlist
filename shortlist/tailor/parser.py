"""Parse Sonnet's tailor output into three named sections.

The model is instructed to emit:

  # RESUME
  ...
  # COVER
  ...
  # NOTES
  ...

This parser splits the response on those headings (case-insensitive,
exact level-1 H1) and returns the bodies. Missing any section raises.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SECTION_RE = re.compile(r"^#\s+(RESUME|COVER|NOTES)\s*$", re.IGNORECASE | re.MULTILINE)


class TailorParseError(ValueError):
    pass


@dataclass(frozen=True)
class TailorSections:
    resume: str
    cover: str
    notes: str


def parse_tailor_output(text: str) -> TailorSections:
    matches = list(_SECTION_RE.finditer(text))
    if len(matches) < 3:
        raise TailorParseError(
            f"expected 3 # H1 sections (RESUME, COVER, NOTES), got {len(matches)}"
        )
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    missing = {"RESUME", "COVER", "NOTES"} - sections.keys()
    if missing:
        raise TailorParseError(f"missing sections: {sorted(missing)}")
    return TailorSections(
        resume=sections["RESUME"],
        cover=sections["COVER"],
        notes=sections["NOTES"],
    )
