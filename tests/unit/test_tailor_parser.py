from pathlib import Path

import pytest

from shortlist.tailor.parser import TailorParseError, parse_tailor_output

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_three_sections():
    text = (FIXTURES / "llm_responses/sonnet_tailor_sample.md").read_text()
    parsed = parse_tailor_output(text)
    assert "David Miller" in parsed.resume
    assert "Hi Acme team," in parsed.cover
    assert "Why this fits:" in parsed.notes


def test_parse_missing_section_raises():
    text = "# RESUME\n\nfoo\n\n# COVER\n\nbar\n"  # no NOTES
    with pytest.raises(TailorParseError):
        parse_tailor_output(text)


def test_parse_strips_section_markers_from_body():
    text = "# RESUME\n\nbody1\n\n# COVER\n\nbody2\n\n# NOTES\n\nbody3\n"
    parsed = parse_tailor_output(text)
    assert parsed.resume == "body1"
    assert parsed.cover == "body2"
    assert parsed.notes == "body3"


def test_parse_handles_extra_whitespace():
    text = "\n\n# RESUME\n\n\nbody1\n\n\n# COVER\n\n\nbody2\n\n# NOTES\n\n\nbody3\n\n\n"
    parsed = parse_tailor_output(text)
    assert parsed.resume == "body1"
    assert parsed.notes == "body3"
