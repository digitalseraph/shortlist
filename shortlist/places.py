"""US place names for search-location validation and autocomplete.

The list is shortlist/data/us_places.txt, built by scripts/build_us_places.py
from GeoNames (CC BY 4.0): one "City, ST" per line, largest places first.
"""

from __future__ import annotations

import importlib.resources
from functools import cache

REMOTE = "Remote"
MIN_QUERY_CHARS = 2


def _normalise(text: str) -> str:
    return " ".join(text.split()).lower()


@cache
def _index() -> tuple[tuple[str, str], ...]:
    """(lowercase, display) pairs: Remote first, then largest places first."""
    data = importlib.resources.files("shortlist").joinpath("data/us_places.txt")
    names = [REMOTE, *data.read_text(encoding="utf-8").splitlines()]
    return tuple((n.lower(), n) for n in names if n)


@cache
def _lookup() -> dict[str, str]:
    # Built from the end so that, for names differing only in case, the
    # earlier (larger) place wins.
    return {low: name for low, name in reversed(_index())}


def canonical(name: str) -> str | None:
    """The list's spelling of `name`, or None when it is not a known place."""
    return _lookup().get(_normalise(name))


def suggest(query: str, limit: int = 10) -> list[str]:
    """Places starting with `query`, then places containing it."""
    q = _normalise(query)
    if len(q) < MIN_QUERY_CHARS:
        return []
    prefix = [name for low, name in _index() if low.startswith(q)]
    contains = [name for low, name in _index() if q in low and not low.startswith(q)]
    return (prefix + contains)[:limit]
