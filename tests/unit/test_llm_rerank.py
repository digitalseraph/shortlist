import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shortlist.ranker.llm_rerank import (
    HAIKU_INPUT_PRICE_PER_MTOK,
    LLMReranker,
    RerankRequest,
    estimate_cost,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _fake_message(text: str, in_tok: int = 100, out_tok: int = 50):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage.input_tokens = in_tok
    msg.usage.output_tokens = out_tok
    return msg


def test_estimate_cost_uses_published_haiku_pricing():
    cost = estimate_cost(input_tokens=1_000_000, output_tokens=0)
    assert cost == pytest.approx(HAIKU_INPUT_PRICE_PER_MTOK, rel=1e-6)


def test_reranker_parses_valid_json_response():
    fixture = json.loads((FIXTURES / "llm_responses/haiku_rerank_sample.json").read_text())
    text = fixture["content"][0]["text"]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_message(text, in_tok=1024, out_tok=96)

    rr = LLMReranker(client=fake_client, model="claude-haiku-4-5-20251001")
    req = RerankRequest(
        resume="Senior backend engineer.",
        prefs_summary="Python, Postgres.",
        candidates=[
            {
                "id": 1,
                "title": "Senior Backend Engineer",
                "company": "Acme",
                "description": "Build distributed systems in Python.",
            },
            {
                "id": 2,
                "title": "Platform Engineer",
                "company": "Globex",
                "description": "Kubernetes platform work.",
            },
        ],
    )
    result = rr.rerank(req)
    assert len(result.scored) == 2
    assert result.scored[0].id == 1
    assert result.scored[0].score == 87
    assert "python" in result.scored[0].reason.lower()
    assert result.cost_usd > 0
    assert result.tokens_in == 1024
    assert result.tokens_out == 96


def test_reranker_retries_once_on_unparsable_output():
    fake_client = MagicMock()
    bad = _fake_message("not JSON at all", 50, 10)
    good_text = '[{"id": 1, "score": 50, "reason": "ok"}]'
    good = _fake_message(good_text, 50, 12)
    fake_client.messages.create.side_effect = [bad, good]

    rr = LLMReranker(client=fake_client, model="claude-haiku-4-5-20251001")
    req = RerankRequest(
        resume="r",
        prefs_summary="p",
        candidates=[{"id": 1, "title": "Eng", "company": "Acme", "description": "x"}],
    )
    result = rr.rerank(req)
    assert len(result.scored) == 1
    assert result.scored[0].score == 50
    assert fake_client.messages.create.call_count == 2


def test_reranker_raises_after_two_failed_parses():
    from shortlist.ranker.llm_rerank import LLMRerankParseError

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _fake_message("garbage 1"),
        _fake_message("garbage 2"),
    ]
    rr = LLMReranker(client=fake_client, model="claude-haiku-4-5-20251001")
    req = RerankRequest(
        resume="r",
        prefs_summary="p",
        candidates=[{"id": 1, "title": "Eng", "company": "Acme", "description": "x"}],
    )
    with pytest.raises(LLMRerankParseError):
        rr.rerank(req)
