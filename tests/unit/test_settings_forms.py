"""Form <-> settings conversion."""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from starlette.datastructures import FormData

from shortlist.config import Prefs
from shortlist_web import settings_forms as sf


def _form(**fields: str | list[str]) -> FormData:
    items: list[tuple[str, str]] = []
    for name, value in fields.items():
        for v in value if isinstance(value, list) else [value]:
            items.append((name, v))
    return FormData(items)


def _prefs(**overrides: object) -> Prefs:
    base: dict[str, object] = {
        "titles": ["French"],
        "locations": [],
        "remote_ok": False,
        "comp_floor_usd": 0,
        "exclude_keywords": [],
        "seniority": [],
    }
    return Prefs.model_validate(base | overrides)


def test_prefs_data_splits_lines_and_reads_checkboxes() -> None:
    data = sf.prefs_data(
        _form(
            titles="French\n\n  World Language \n",
            search_locations=["Brunswick, GA", "", "Remote"],
            remote_ok="on",
            comp_floor_usd="0",
        )
    )
    assert data["titles"] == ["French", "World Language"]
    assert data["search_locations"] == ["Brunswick, GA", "Remote"]
    assert data["remote_ok"] is True
    assert data["hn_enabled"] is False
    assert data["comp_floor_usd"] == "0"


def test_prefs_values_round_trip() -> None:
    values = sf.prefs_values(_prefs(locations=["GA"], search_locations=["Remote"]))
    assert values["titles"] == ["French"]
    assert values["search_locations"] == ["Remote"]


def test_field_errors_maps_to_form_names() -> None:
    with pytest.raises(ValidationError) as info:
        Prefs.model_validate(sf.prefs_data(_form(search_locations=["Brunswik, GA"])))
    errors = sf.field_errors(info.value, sf.PREFS_ERROR_NAMES)
    assert errors["search_locations"] == "not a known place: 'Brunswik, GA'"
    assert "titles" in errors
    assert "comp_floor_usd" in errors


def test_to_yaml_writes_header_and_loads_back() -> None:
    prefs = _prefs()
    text = sf.to_yaml(sf.PREFS_HEADER, prefs)
    assert text.startswith("#")
    assert Prefs.model_validate(yaml.safe_load(text)) == prefs


def test_config_data_updates_only_form_fields() -> None:
    current: dict[str, Any] = {
        "anthropic": {"key_source": "env", "key_env_var": "OLD"},
        "budget": {"daily_usd": 5.0, "monthly_usd": 60.0},
        "sources": {"rss": {"enabled": True}},
    }
    data = sf.config_data(_form(key_env_var="NEW", daily_usd="6", pdf_template=""), current)
    assert data["anthropic"] == {"key_source": "env", "key_env_var": "NEW"}
    assert data["budget"]["daily_usd"] == "6"
    assert data["sources"] == {"rss": {"enabled": True}}
    assert data["paths"]["pdf_template"] is None
    assert current["anthropic"]["key_env_var"] == "OLD"  # input not mutated


def test_config_values_reads_nested_fields() -> None:
    values = sf.config_values({"tailor": {"model": "m", "cover_paragraphs": 3}})
    assert values["tailor_model"] == "m"
    assert values["cover_paragraphs"] == 3
    assert values["daily_usd"] is None


def test_current_config_falls_back_to_default() -> None:
    assert "ranker" in sf.current_config(None)
