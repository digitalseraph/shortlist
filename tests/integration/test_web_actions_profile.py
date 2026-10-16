"""Background work is pinned to the profile that enqueued it."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist.models import RawJob
from shortlist.store import db as store_db
from shortlist_web.app import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _seed(db: Path, eid: str, company: str) -> int:
    job = store_db.upsert_job(
        db,
        RawJob(
            source="greenhouse",
            external_id=eid,
            company=company,
            title="Senior Backend Engineer",
            url=f"https://example.com/{eid}",
            posted_at=datetime.now(UTC),
        ),
    )
    return job.id


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def test_status_feed_only_shows_this_profile(client: TestClient) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    client.app.state.task_log = [
        ("david", "10:00:00", "fetch done: 3 jobs"),
        ("alex", "10:00:01", "fetch done: 7 jobs"),
    ]
    mine = client.get("/p/david/status")
    assert "3 jobs" in mine.text
    assert "7 jobs" not in mine.text


def test_purge_acts_on_the_url_profile(client: TestClient) -> None:
    david = profiles.create("david", "David")
    profiles.create("alex", "Alex")
    r = client.post("/p/alex/jobs/purge-untailored")
    assert r.status_code == 200
    assert client.app.state.task_log[-1][0] == "alex"
    assert david.db_path.exists()


def test_fetch_writes_to_the_url_profile_not_the_env_active_one(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fetch enqueued for `david` must write to david's database even when
    something else (here: $SHORTLIST_PROFILE) claims a different profile is
    'active' by the time the background task actually runs. The handler must
    capture david's db_path/slug at enqueue time and the `_run_fetch` wrapper
    must use exactly that — never re-resolve a profile from ambient state.
    """
    david = profiles.create("david", "David")
    alex = profiles.create("alex", "Alex")

    def fake_fetch_all(db_path: Path, prefs: object, *, progress: object = None) -> str:
        # Prove which db this background run actually touched.
        store_db.mark_source_fetched(db_path, "fake", datetime.now(UTC))
        return "fetched 1"

    monkeypatch.setattr("shortlist_web.routes.actions.fetch_all", fake_fetch_all)
    # Simulate a profile switch that happens before the background task runs:
    # whatever resolve()-based logic would see "alex" as active right now.
    monkeypatch.setenv("SHORTLIST_PROFILE", "alex")

    r = client.post("/p/david/fetch")

    assert r.status_code == 200
    assert store_db.source_last_fetched(david.db_path, "fake") is not None
    assert store_db.source_last_fetched(alex.db_path, "fake") is None
    assert client.app.state.task_log[-1][0] == "david"


def test_tailor_writes_under_the_profiles_own_output_dir(
    client: TestClient, env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tailor run enqueued through the web must land under THAT profile's
    own output_dir. The shared config.yaml's `paths.output_dir` is legacy and
    unused — jobs are {company}-{title}-{job.id}, and job ids autoincrement
    per database, so two people who fetched the same posting would otherwise
    collide on the exact same path in a shared directory.
    """
    david = profiles.create("david", "David")
    jid = _seed(david.db_path, "gh_1", "Acme")
    david.resume_path.parent.mkdir(parents=True, exist_ok=True)
    david.resume_path.write_text("# David's resume\n")

    decoy_output = env / "decoy-shared-output"
    cfg_path = env / "config" / "config.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "anthropic:\n"
        "  key_source: env\n"
        "  key_env_var: ANTHROPIC_API_KEY\n"
        "budget:\n"
        "  daily_usd: 5.0\n"
        "  monthly_usd: 60.0\n"
        "paths:\n"
        f"  resume: {david.resume_path}\n"
        f"  output_dir: {decoy_output}\n"
        "sources: {}\n"
        "ranker:\n"
        "  top_k_for_llm_rerank: 30\n"
        "  embedding_model: bge-small-en-v1.5\n"
        "  rerank_model: claude-haiku-4-5-20251001\n"
        "tailor:\n"
        "  model: claude-sonnet-4-6\n"
        "  cover_paragraphs: 3\n"
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    fixture = FIXTURES / "llm_responses/sonnet_tailor_sample.md"
    msg = MagicMock()
    msg.content = [MagicMock(text=fixture.read_text())]
    msg.usage.input_tokens = 1500
    msg.usage.output_tokens = 1200
    fake_anth = MagicMock()
    fake_anth.messages.create.return_value = msg
    # actions.py imports Anthropic lazily inside the route, so patch the SDK's
    # own symbol rather than a (nonexistent) module-level one in actions.py.
    monkeypatch.setattr("anthropic.Anthropic", lambda **_kw: fake_anth)

    r = client.post(f"/p/david/tailor/{jid}")
    assert r.status_code == 200

    assert any(david.output_dir.iterdir()), "nothing was written under the profile's output_dir"
    assert not decoy_output.exists(), "the shared/legacy cfg.paths.output_dir must never be used"
