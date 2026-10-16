"""Convert the settings forms to and from the pydantic settings models.

The forms post flat fields; the models want lists, booleans and numbers.
Validation stays in the models, so a form save and a YAML save obey the
same rules.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError
from starlette.datastructures import FormData

from shortlist.config import DEFAULT_CONFIG_YAML, Prefs

PREFS_HEADER = "# Shortlist preferences. Saved from the settings form.\n"
CONFIG_HEADER = "# Shortlist configuration. Saved from the settings form.\n"

# One item per line in a textarea.
LINE_FIELDS = (
    "titles",
    "seniority",
    "exclude_keywords",
    "indeed_queries",
    "linkedin_queries",
    "glassdoor_queries",
    "wellfound_queries",
    "otta_queries",
    "greenhouse_companies",
    "lever_companies",
    "ashby_companies",
    "workable_companies",
    "smartrecruiters_companies",
    "rss_urls",
)
# One input per location, with suggestions.
LOCATION_FIELDS = ("locations", "search_locations")
BOOL_FIELDS = ("remote_ok", "hn_enabled", "remoteok_enabled", "remotive_enabled")

PREFS_ERROR_NAMES: Mapping[tuple[str, ...], str] = {(f,): f for f in Prefs.model_fields}

# Form field name -> (section, key) in config.yaml. Anything not listed here
# (anthropic.key_source, sources, legacy paths) is never shown and is kept.
CONFIG_FIELDS: Mapping[str, tuple[str, str]] = {
    "key_env_var": ("anthropic", "key_env_var"),
    "daily_usd": ("budget", "daily_usd"),
    "monthly_usd": ("budget", "monthly_usd"),
    "embedding_model": ("ranker", "embedding_model"),
    "rerank_model": ("ranker", "rerank_model"),
    "top_k_for_llm_rerank": ("ranker", "top_k_for_llm_rerank"),
    "tailor_model": ("tailor", "model"),
    "cover_paragraphs": ("tailor", "cover_paragraphs"),
    "pdf_template": ("paths", "pdf_template"),
}
CONFIG_ERROR_NAMES: Mapping[tuple[str, ...], str] = {
    path: name for name, path in CONFIG_FIELDS.items()
}


def _lines(text: str) -> list[str]:
    return [s.strip() for s in text.splitlines() if s.strip()]


def prefs_data(form: FormData) -> dict[str, object]:
    """The prefs form as a dict ready for `Prefs.model_validate`."""
    data: dict[str, object] = {f: _lines(str(form.get(f, ""))) for f in LINE_FIELDS}
    for f in LOCATION_FIELDS:
        data[f] = [str(v).strip() for v in form.getlist(f) if str(v).strip()]
    for f in BOOL_FIELDS:
        data[f] = f in form
    # Left as text: pydantic parses it, and reports a bad number on the field.
    data["comp_floor_usd"] = str(form.get("comp_floor_usd", "")).strip()
    return data


def prefs_values(prefs: Prefs) -> dict[str, object]:
    """Field values for rendering the prefs form."""
    return prefs.model_dump()


def config_data(form: FormData, current: dict[str, Any]) -> dict[str, Any]:
    """`current` config with the form's fields replaced; `current` is not changed."""
    data = copy.deepcopy(current)
    for name, (section, key) in CONFIG_FIELDS.items():
        value: str | None = str(form.get(name, "")).strip()
        if name == "pdf_template" and not value:
            value = None  # optional path: empty means unset
        data.setdefault(section, {})[key] = value
    return data


def config_values(current: dict[str, Any]) -> dict[str, object]:
    """Form values read out of a config dict."""
    return {
        name: (current.get(section) or {}).get(key)
        for name, (section, key) in CONFIG_FIELDS.items()
    }


def current_config(text: str | None) -> dict[str, Any]:
    """The config file's data, or the built-in default when there is no file."""
    data = yaml.safe_load(text if text is not None else DEFAULT_CONFIG_YAML)
    return data if isinstance(data, dict) else {}


def field_errors(exc: ValidationError, names: Mapping[tuple[str, ...], str]) -> dict[str, str]:
    """First error message per form field, keyed by the field's form name.

    `names` maps a pydantic error location (its first one or two parts) to a
    form field name. Errors with no matching field are keyed "_form".
    """
    out: dict[str, str] = {}
    for err in exc.errors():
        loc = tuple(str(part) for part in err["loc"])
        name = names.get(loc[:2]) or names.get(loc[:1]) or "_form"
        out.setdefault(name, err["msg"].removeprefix("Value error, "))
    return out


def to_yaml(header: str, model: BaseModel) -> str:
    """YAML for `model` as given (unset defaults and None left out)."""
    data = model.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    return header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
