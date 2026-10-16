"""Upload shows a preview; only an explicit save writes resume.md."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist.resume_import import MAX_RESUME_BYTES
from shortlist_web.app import create_app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def test_upload_previews_without_writing(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    r = client.post(
        "/p/david/resume/upload",
        files={"file": ("resume.md", b"# David\n\nStaff Engineer", "text/markdown")},
    )
    assert r.status_code == 200
    assert "Staff Engineer" in r.text
    assert not prof.resume_path.exists()


def test_save_writes_resume_md(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    r = client.post("/p/david/resume", data={"text": "# David\n\nStaff Engineer"})
    assert r.status_code == 200
    assert prof.resume_path.read_text() == "# David\n\nStaff Engineer"


def test_upload_keeps_the_original_file(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    client.post(
        "/p/david/resume/upload",
        files={"file": ("resume.md", b"# David", "text/markdown")},
    )
    assert prof.original_resume_path.read_bytes() == b"# David"


def test_unsupported_upload_rejected(client: TestClient) -> None:
    profiles.create("david", "David")
    r = client.post(
        "/p/david/resume/upload",
        files={"file": ("resume.rtf", b"{\\rtf1}", "application/rtf")},
    )
    assert r.status_code == 400


def test_editor_prefills_from_disk(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    prof.resume_path.write_text("# Existing resume")
    r = client.get("/p/david/resume")
    assert "# Existing resume" in r.text


def test_save_bumps_mtime_so_the_embedding_cache_misses(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    prof.resume_path.write_text("old")
    before = prof.resume_path.stat().st_mtime_ns
    client.post("/p/david/resume", data={"text": "new"})
    assert prof.resume_path.stat().st_mtime_ns != before


def test_upload_filename_cannot_escape_the_profile(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    client.post(
        "/p/david/resume/upload",
        files={"file": ("../../evil.md", b"x", "text/markdown")},
    )
    data_root = prof.db_path.parent
    assert not (data_root.parent.parent / "evil.md").exists()
    assert prof.original_resume_path.exists()


def test_oversized_upload_is_rejected(client: TestClient) -> None:
    """The route bounds its own read before extraction, not after.

    `extract_text` already rejects anything over MAX_RESUME_BYTES, but the
    route must not read the whole file into memory first to find that out -
    it reads at most MAX_RESUME_BYTES + 1 bytes, which is already enough to
    trigger the same rejection for a file this size or any larger one.
    """
    prof = profiles.create("david", "David")
    oversized = b"x" * (MAX_RESUME_BYTES + 1)
    r = client.post(
        "/p/david/resume/upload",
        files={"file": ("resume.txt", oversized, "text/plain")},
    )
    assert r.status_code == 400
    assert not prof.original_resume_path.exists()
