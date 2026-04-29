"""Anthropic Haiku rerank client.

Sends a batch of candidate jobs (already passed hard filter + cosine top-K)
to claude-haiku-4-5 and parses a JSON list of {id, score, reason} back.

One retry with a corrective system prompt if the first response is
unparsable. Surfaces cost + token usage so the caller can record it in
`scoring_runs`.

Pricing (USD per 1M tokens, public Anthropic pricing as of 2026-01):
  Haiku 4.5 input  : $0.80
  Haiku 4.5 output : $4.00
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

HAIKU_INPUT_PRICE_PER_MTOK = 0.80
HAIKU_OUTPUT_PRICE_PER_MTOK = 4.00


def estimate_cost(*, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * HAIKU_INPUT_PRICE_PER_MTOK
        + output_tokens / 1_000_000 * HAIKU_OUTPUT_PRICE_PER_MTOK
    )


class LLMRerankParseError(RuntimeError):
    pass


@dataclass(frozen=True)
class RerankRequest:
    resume: str
    prefs_summary: str
    candidates: list[dict[str, Any]]  # each: {id, title, company, description}


@dataclass(frozen=True)
class ScoredJob:
    id: int
    score: int
    reason: str


@dataclass(frozen=True)
class RerankResult:
    scored: list[ScoredJob]
    cost_usd: float
    tokens_in: int
    tokens_out: int


_SYSTEM = (
    "You rank job postings against a candidate's resume and stated preferences. "
    "Return ONLY a JSON array. Each element: "
    '{"id": <int>, "score": 0-100 int, "reason": "<one line>"}. '
    "No prose outside the JSON. No markdown fences. "
    "Score by fit (skills + seniority + domain), not by job desirability."
)

_CORRECTIVE = (
    "Your previous response was not valid JSON. "
    "Return ONLY a JSON array of {id, score, reason}. No other text."
)


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        raise LLMRerankParseError("no JSON array found in response")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMRerankParseError(f"invalid JSON: {e}") from e
    if not isinstance(data, list):
        raise LLMRerankParseError("parsed JSON is not a list")
    return data


def _build_user_prompt(req: RerankRequest) -> str:
    lines = [
        "RESUME:",
        req.resume.strip(),
        "",
        "PREFERENCES:",
        req.prefs_summary.strip(),
        "",
        "CANDIDATES (rank these):",
    ]
    for c in req.candidates:
        lines.append(
            f"- id={c['id']} | {c['company']} — {c['title']}\n  {c.get('description', '')[:600]}"
        )
    return "\n".join(lines)


class LLMReranker:
    def __init__(
        self, *, client: Any, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 4096
    ):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def rerank(self, req: RerankRequest) -> RerankResult:
        user = _build_user_prompt(req)
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = msg.content[0].text
        in_tok = int(msg.usage.input_tokens)
        out_tok = int(msg.usage.output_tokens)
        try:
            parsed = _extract_json_array(text)
        except LLMRerankParseError:
            logger.warning("haiku rerank: first parse failed, retrying with corrective prompt")
            msg2 = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_SYSTEM + "\n" + _CORRECTIVE,
                messages=[
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": _CORRECTIVE},
                ],
            )
            in_tok += int(msg2.usage.input_tokens)
            out_tok += int(msg2.usage.output_tokens)
            parsed = _extract_json_array(msg2.content[0].text)

        scored = [
            ScoredJob(
                id=int(item["id"]),
                score=max(0, min(100, int(item["score"]))),
                reason=str(item.get("reason", "")).strip()[:200],
            )
            for item in parsed
            if "id" in item and "score" in item
        ]
        return RerankResult(
            scored=scored,
            cost_usd=estimate_cost(input_tokens=in_tok, output_tokens=out_tok),
            tokens_in=in_tok,
            tokens_out=out_tok,
        )
