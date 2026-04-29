import json
from pathlib import Path
from unittest.mock import MagicMock

from shortlist.sources.curated.hn_who_hiring import (
    find_latest_thread_id,
    parse_comment,
    parse_thread,
)

FIXTURES = Path(__file__).parent.parent / "fixtures/curated"


def test_find_latest_thread_id_returns_newest():
    payload = json.loads((FIXTURES / "hn_algolia_search.json").read_text())
    fake_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    fake_client.get.return_value = resp
    assert find_latest_thread_id(fake_client) == 44000001


def test_parse_thread_extracts_jobs():
    payload = json.loads((FIXTURES / "hn_thread_comments.json").read_text())
    jobs = parse_thread(payload)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "hn_who_hiring"
    assert j0.external_id == "44000100"
    assert j0.company == "Acme Inc"
    assert j0.remote is True
    assert "acme.example" in str(j0.url)


def test_parse_comment_returns_none_for_non_job_post():
    comment = {
        "id": 999,
        "type": "comment",
        "text": "<p>Just a regular comment, not a job post.",
        "created_at_i": 1746676800,
    }
    assert parse_comment(comment) is None
