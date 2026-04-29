from pathlib import Path

from shortlist.sources.feeds.rss import parse_feed

FIXTURES = Path(__file__).parent.parent / "fixtures/feeds"


def test_parse_sample_rss():
    content = (FIXTURES / "sample.rss").read_text()
    jobs = parse_feed(content, feed_url="https://acme.example/feed.rss")
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "rss"
    assert j0.title == "Senior Backend Engineer"
    assert j0.company == "Acme Careers"
    assert j0.remote is True
    assert "acme.example" in j0.external_id


def test_parse_empty_feed():
    jobs = parse_feed("<rss><channel></channel></rss>", feed_url="x")
    assert jobs == []
