from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortlist.store.db import (
    clear_source_cooldown,
    is_source_in_cooldown,
    mark_source_cooldown,
    migrate,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "db.sqlite"


def test_no_cooldown_by_default(db_path):
    migrate(db_path)
    assert is_source_in_cooldown(db_path, "indeed") is False


def test_mark_then_check_cooldown(db_path):
    migrate(db_path)
    until = datetime.now(UTC) + timedelta(hours=24)
    mark_source_cooldown(db_path, "indeed", until=until)
    assert is_source_in_cooldown(db_path, "indeed") is True


def test_expired_cooldown_returns_false(db_path):
    migrate(db_path)
    past = datetime.now(UTC) - timedelta(hours=1)
    mark_source_cooldown(db_path, "indeed", until=past)
    assert is_source_in_cooldown(db_path, "indeed") is False


def test_clear_cooldown(db_path):
    migrate(db_path)
    until = datetime.now(UTC) + timedelta(hours=24)
    mark_source_cooldown(db_path, "indeed", until=until)
    clear_source_cooldown(db_path, "indeed")
    assert is_source_in_cooldown(db_path, "indeed") is False
