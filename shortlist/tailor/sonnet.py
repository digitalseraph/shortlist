"""Sonnet tailor client.

Pricing (USD per 1M tokens, public Anthropic pricing as of 2026-01):
  Sonnet 4.6 input  : $3.00
  Sonnet 4.6 output : $15.00
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from shortlist.tailor.parser import (
    TailorParseError,
    TailorSections,
    parse_tailor_output,
)
from shortlist.tailor.prompt import SYSTEM, build_user_prompt

logger = logging.getLogger(__name__)

SONNET_INPUT_PRICE_PER_MTOK = 3.00
SONNET_OUTPUT_PRICE_PER_MTOK = 15.00


def estimate_tailor_cost(*, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * SONNET_INPUT_PRICE_PER_MTOK
        + output_tokens / 1_000_000 * SONNET_OUTPUT_PRICE_PER_MTOK
    )


@dataclass(frozen=True)
class TailorRequest:
    resume: str
    prefs_summary: str
    job_title: str
    company: str
    job_description: str
    cover_paragraphs: int = 3


@dataclass(frozen=True)
class TailorResult:
    sections: TailorSections
    cost_usd: float
    tokens_in: int
    tokens_out: int


class SonnetTailorClient:
    def __init__(
        self,
        *,
        client: Any,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 8192,
    ):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def tailor(self, req: TailorRequest) -> TailorResult:
        user = build_user_prompt(
            resume=req.resume,
            prefs_summary=req.prefs_summary,
            job_title=req.job_title,
            company=req.company,
            job_description=req.job_description,
            cover_paragraphs=req.cover_paragraphs,
        )
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = msg.content[0].text
        in_tok = int(msg.usage.input_tokens)
        out_tok = int(msg.usage.output_tokens)
        try:
            sections = parse_tailor_output(text)
        except TailorParseError:
            logger.warning("sonnet tailor: first parse failed, retrying once")
            corrective = (
                "Your previous response was not in the required format. Output "
                "EXACTLY three top-level H1 sections in order: # RESUME, # COVER, "
                "# NOTES. No prose outside them."
            )
            msg2 = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=SYSTEM + "\n" + corrective,
                messages=[
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": corrective},
                ],
            )
            in_tok += int(msg2.usage.input_tokens)
            out_tok += int(msg2.usage.output_tokens)
            sections = parse_tailor_output(msg2.content[0].text)
        return TailorResult(
            sections=sections,
            cost_usd=estimate_tailor_cost(input_tokens=in_tok, output_tokens=out_tok),
            tokens_in=in_tok,
            tokens_out=out_tok,
        )
