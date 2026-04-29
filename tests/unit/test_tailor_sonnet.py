from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shortlist.tailor.sonnet import (
    SONNET_INPUT_PRICE_PER_MTOK,
    SonnetTailorClient,
    TailorRequest,
    estimate_tailor_cost,
)


def _fake_msg(text: str, in_tok: int = 2000, out_tok: int = 1500):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage.input_tokens = in_tok
    msg.usage.output_tokens = out_tok
    return msg


def test_estimate_tailor_cost():
    cost = estimate_tailor_cost(input_tokens=1_000_000, output_tokens=0)
    assert cost == pytest.approx(SONNET_INPUT_PRICE_PER_MTOK, rel=1e-6)


def test_sonnet_tailor_returns_3_sections():
    fixture = Path(__file__).parent.parent / "fixtures/llm_responses/sonnet_tailor_sample.md"
    text = fixture.read_text()
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_msg(text, 2000, 1500)

    client = SonnetTailorClient(client=fake_client, model="claude-sonnet-4-6")
    req = TailorRequest(
        resume="My resume.",
        prefs_summary="Python, Postgres.",
        job_title="Senior Backend Engineer",
        company="Acme",
        job_description="Build distributed systems.",
        cover_paragraphs=3,
    )
    result = client.tailor(req)
    assert "David Miller" in result.sections.resume
    assert "Hi Acme team," in result.sections.cover
    assert "Why this fits:" in result.sections.notes
    assert result.cost_usd > 0
    assert result.tokens_in == 2000
    assert result.tokens_out == 1500


def test_sonnet_tailor_retries_on_parse_failure():
    fixture = Path(__file__).parent.parent / "fixtures/llm_responses/sonnet_tailor_sample.md"
    good = fixture.read_text()
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _fake_msg("not valid output", 1000, 50),
        _fake_msg(good, 1500, 1500),
    ]
    client = SonnetTailorClient(client=fake_client, model="claude-sonnet-4-6")
    req = TailorRequest(
        resume="r",
        prefs_summary="p",
        job_title="t",
        company="c",
        job_description="d",
        cover_paragraphs=3,
    )
    result = client.tailor(req)
    assert "David Miller" in result.sections.resume
    assert fake_client.messages.create.call_count == 2
