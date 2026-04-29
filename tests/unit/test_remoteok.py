import json
from pathlib import Path

from shortlist.sources.curated.remoteok import parse_payload

FIXTURES = Path(__file__).parent.parent / "fixtures/curated"


def test_parse_remoteok_payload():
    items = json.loads((FIXTURES / "remoteok_api.json").read_text())
    jobs = parse_payload(items)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "remoteok"
    assert j0.external_id == "rok_1001"
    assert j0.company == "Acme"
    assert j0.title == "Senior Backend Engineer"
    assert j0.remote is True
    assert j0.comp_min == 200000


def test_parse_skips_legal_blob():
    items = [{"legal": "Copyright RemoteOK"}]
    jobs = parse_payload(items)
    assert jobs == []
