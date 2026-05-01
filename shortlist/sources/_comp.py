"""Compensation parsing from free-form text.

Extracts (comp_min, comp_max) from strings like:
  "$200k - $240k"           → (200000, 240000)
  "$200,000 to $240,000"    → (200000, 240000)
  "$200K-240K"              → (200000, 240000)
  "$45/hr"                  → (45, 45)
  "$45-75 per hour"         → (45, 75)
  "USD 180k+"               → (180000, None)
  "Salary: 150-180k EUR"    → (150000, 180000)

Returns (None, None) if no plausible amount is found. Heuristic only —
some text contains revenue, head-count, or other dollar amounts that get
misread. Use the structured field when a source provides one and fall
back here for description-text mining.
"""

from __future__ import annotations

import re

# Match a single dollar amount: optional $, MUST start with a digit (otherwise
# bare commas / dots match and produce empty captures), optional commas inside,
# optional decimal, optional k/K/m/M suffix.
_AMOUNT = r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?"

# Range: AMOUNT separator AMOUNT, with optional "$" on right side and
# common separators (-, –, —, "to").
_RANGE_RE = re.compile(
    rf"{_AMOUNT}\s*(?:-|–|—|to)\s*{_AMOUNT}",
)

# Single amount near a money word ("salary", "comp", "$", "USD", "/hr"…).
_SINGLE_RE = re.compile(
    rf"(?:salary|compensation|comp|pay|rate|usd|eur|gbp|\$)[\s:]*{_AMOUNT}\b",
    re.IGNORECASE,
)

# Hourly indicator near a number — keys "/hr", "per hour", "hourly".
_HOURLY_RE = re.compile(r"/\s*hr|/\s*hour|per\s+hour|hourly", re.IGNORECASE)

# Reject obvious false positives: amounts followed by "employees", "users",
# "customers", "revenue", "ARR", "MRR", "valuation" — those are company
# scale numbers, not comp.
_REJECT_RE = re.compile(
    r"\b(employees|users|customers|revenue|arr|mrr|valuation|funded|raised|"
    r"members|seed|series\s+[a-z])\b",
    re.IGNORECASE,
)


def _to_int(num: str, suffix: str | None, *, hourly: bool = False) -> int:
    """Convert a captured (digits, suffix) into an int dollar amount.

    Returns 0 on degenerate input (empty after comma strip); caller's
    range checks reject zeros downstream.
    """
    cleaned = num.replace(",", "").strip()
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        return 0
    n = float(cleaned)
    if suffix and suffix.lower() == "k":
        n *= 1000
    elif suffix and suffix.lower() == "m":
        n *= 1_000_000
    elif not suffix and not hourly and n < 1000:
        # Bare "150" with no k/m and not hourly almost certainly means 150k.
        # (Real hourly rates land in the $20-$300 range, but the hourly path
        # below handles those explicitly via _HOURLY_RE.)
        n *= 1000
    return int(n)


def parse_comp_from_text(text: str) -> tuple[int | None, int | None]:
    """Return (min, max) extracted from free-form text, or (None, None)."""
    if not text:
        return None, None

    sample = text[:500]
    hourly = bool(_HOURLY_RE.search(sample))

    # Try range first (most common for job postings).
    for m in _RANGE_RE.finditer(text):
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        window = text[start:end]
        if _REJECT_RE.search(window):
            continue
        lo = _to_int(m.group(1), m.group(2), hourly=hourly)
        hi = _to_int(m.group(3), m.group(4), hourly=hourly)
        if lo > hi:
            lo, hi = hi, lo
        if hourly:
            if 5 <= lo <= 500 and 5 <= hi <= 500:
                return lo, hi
        else:
            if 30_000 <= lo <= 5_000_000 and 30_000 <= hi <= 5_000_000:
                return lo, hi

    # Fall back: single amount near a money word.
    for m in _SINGLE_RE.finditer(text):
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        window = text[start:end]
        if _REJECT_RE.search(window):
            continue
        n = _to_int(m.group(1), m.group(2), hourly=hourly)
        if hourly:
            if 5 <= n <= 500:
                return n, n
        else:
            if 30_000 <= n <= 5_000_000:
                return n, n

    return None, None
