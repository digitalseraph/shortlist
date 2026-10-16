"""Bundled US place list: validation and autocomplete."""

from __future__ import annotations

import pytest

from shortlist import places


def test_canonical_ignores_case_and_spacing() -> None:
    assert places.canonical("  brunswick,   ga ") == "Brunswick, GA"


def test_canonical_rejects_unknown_place() -> None:
    assert places.canonical("Brunswik, GA") is None


def test_remote_is_a_place() -> None:
    assert places.canonical("remote") == "Remote"


def test_suggest_finds_brunswick() -> None:
    assert "Brunswick, GA" in places.suggest("brun")


def test_suggest_short_query_returns_nothing() -> None:
    assert places.suggest("b") == []


def test_suggest_respects_limit() -> None:
    assert len(places.suggest("sa", limit=3)) == 3


def test_suggest_puts_prefix_matches_first(monkeypatch: pytest.MonkeyPatch) -> None:
    names = ["East Augusta, GA", "Augusta, GA", "Augusta, ME"]
    monkeypatch.setattr(places, "_index", lambda: tuple((n.lower(), n) for n in names))
    assert places.suggest("augusta") == ["Augusta, GA", "Augusta, ME", "East Augusta, GA"]
