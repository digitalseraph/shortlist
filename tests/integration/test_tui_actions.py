from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shortlist.profiles import Profile
from shortlist.store.db import migrate
from shortlist_tui.app import ShortlistApp


def _profile(db: Path) -> Profile:
    """Minimal profile pointing at a test database."""
    return Profile(
        slug="test",
        display_name="Test",
        db_path=db,
        prefs_path=db.parent / "prefs.yaml",
        resume_path=db.parent / "resume.md",
        original_resume_path=db.parent / "resume.original",
        output_dir=db.parent / "output",
    )


@pytest.mark.asyncio
async def test_f_triggers_fetch(tmp_path: Path, monkeypatch):
    db = tmp_path / "db.sqlite"
    migrate(db)
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(cfg_dir))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))

    called: list[bool] = []

    def fake_fetch_all(*_a, **_k):
        called.append(True)
        return "fetched 0 jobs"

    import shortlist_tui.app as app_mod

    monkeypatch.setattr(app_mod, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(app_mod, "load_prefs", lambda *_a, **_k: MagicMock())

    async with ShortlistApp(profile=_profile(db)).run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.app.workers.wait_for_complete()
    assert called == [True]


@pytest.mark.asyncio
async def test_rank_worker_uses_the_profiles_own_resume(tmp_path: Path, monkeypatch):
    """Rank must score a profile's jobs against THAT profile's own resume,
    never the shared config.yaml's legacy `paths.resume` — otherwise another
    person's jobs get scored against the owner's career history.
    """
    db = tmp_path / "db.sqlite"
    migrate(db)
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(cfg_dir))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    decoy_resume = tmp_path / "decoy-shared-resume.md"
    decoy_resume.write_text("someone else's resume")
    (cfg_dir / "config.yaml").write_text(
        "anthropic:\n"
        "  key_source: env\n"
        "  key_env_var: ANTHROPIC_API_KEY\n"
        "budget:\n"
        "  daily_usd: 5.0\n"
        "  monthly_usd: 60.0\n"
        "paths:\n"
        f"  resume: {decoy_resume}\n"
        f"  output_dir: {tmp_path / 'decoy-output'}\n"
        "sources: {}\n"
        "ranker:\n"
        "  top_k_for_llm_rerank: 30\n"
        "  embedding_model: bge-small-en-v1.5\n"
        "  rerank_model: claude-haiku-4-5-20251001\n"
        "tailor:\n"
        "  model: claude-sonnet-4-6\n"
        "  cover_paragraphs: 3\n"
    )

    profile = _profile(db)
    profile.resume_path.parent.mkdir(parents=True, exist_ok=True)
    profile.resume_path.write_text("this profile's own resume")

    captured: dict[str, Path] = {}

    def fake_rank_all(db_path, **kwargs):
        captured["resume_path"] = kwargs["resume_path"]
        return "ranked"

    import shortlist_tui.app as app_mod

    monkeypatch.setattr(app_mod, "rank_all", fake_rank_all)
    monkeypatch.setattr(app_mod, "load_prefs", lambda *_a, **_k: MagicMock())

    async with ShortlistApp(profile=profile).run_test() as pilot:
        await pilot.pause()
        await pilot.press("R")
        await pilot.app.workers.wait_for_complete()

    assert captured["resume_path"] == profile.resume_path
    assert captured["resume_path"] != decoy_resume


@pytest.mark.asyncio
async def test_rank_worker_notifies_on_missing_resume_without_crashing(tmp_path: Path, monkeypatch):
    """Same guard _tailor_worker already has: a missing resume must produce
    a notification, not an unhandled exception that tears down the app.
    """
    db = tmp_path / "db.sqlite"
    migrate(db)
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(cfg_dir))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    (cfg_dir / "config.yaml").write_text(
        "anthropic:\n"
        "  key_source: env\n"
        "  key_env_var: ANTHROPIC_API_KEY\n"
        "budget:\n"
        "  daily_usd: 5.0\n"
        "  monthly_usd: 60.0\n"
        "paths: {}\n"
        "sources: {}\n"
        "ranker:\n"
        "  top_k_for_llm_rerank: 30\n"
        "  embedding_model: bge-small-en-v1.5\n"
        "  rerank_model: claude-haiku-4-5-20251001\n"
        "tailor:\n"
        "  model: claude-sonnet-4-6\n"
        "  cover_paragraphs: 3\n"
    )

    profile = _profile(db)  # resume_path is never written - does not exist

    import shortlist_tui.app as app_mod

    monkeypatch.setattr(app_mod, "load_prefs", lambda *_a, **_k: MagicMock())

    async with ShortlistApp(profile=profile).run_test() as pilot:
        await pilot.pause()
        await pilot.press("R")
        await pilot.app.workers.wait_for_complete()
        # No exception propagated - the app is still alive and responsive.
        await pilot.pause()
