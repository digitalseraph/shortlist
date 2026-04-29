from pathlib import Path

import pytest
from pydantic import ValidationError

from shortlist.config import Config, Prefs, load_config, load_prefs

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_load_config_defaults():
    cfg = load_config(FIXTURES / "config_default.yaml")
    assert cfg.anthropic.key_env_var == "ANTHROPIC_API_KEY"
    assert cfg.budget.daily_usd == 5.0
    assert cfg.sources["greenhouse"].enabled is True
    assert cfg.sources["greenhouse"].rate_limit_rpm == 30


def test_load_prefs_defaults():
    prefs = load_prefs(FIXTURES / "prefs_default.yaml")
    assert "Senior Backend Engineer" in prefs.titles
    assert prefs.comp_floor_usd == 180000
    assert "acme" in prefs.greenhouse_companies


def test_config_rejects_negative_budget():
    with pytest.raises(ValidationError):
        Config.model_validate(
            {
                "anthropic": {"key_source": "env", "key_env_var": "X"},
                "budget": {"daily_usd": -1.0, "monthly_usd": 60.0},
                "paths": {"resume": "~/r.md", "output_dir": "~/jobs"},
                "sources": {},
                "ranker": {
                    "top_k_for_llm_rerank": 30,
                    "embedding_model": "bge",
                    "rerank_model": "x",
                },
                "tailor": {"model": "x", "cover_paragraphs": 3},
            }
        )


def test_prefs_rejects_empty_titles():
    with pytest.raises(ValidationError):
        Prefs.model_validate(
            {
                "titles": [],
                "locations": ["Remote"],
                "remote_ok": True,
                "comp_floor_usd": 100000,
                "exclude_keywords": [],
                "seniority": [],
                "greenhouse_companies": [],
            }
        )


def test_load_prefs_includes_all_ats_company_lists():
    prefs = load_prefs(FIXTURES / "prefs_default.yaml")
    assert prefs.lever_companies == ["acme"]
    assert prefs.ashby_companies == ["acme"]
    assert prefs.workable_companies == ["acme"]
    assert prefs.smartrecruiters_companies == ["Acme"]


def test_prefs_defaults_to_empty_lists_when_omitted():
    p = Prefs.model_validate(
        {
            "titles": ["Eng"],
            "locations": ["Remote"],
            "remote_ok": True,
            "comp_floor_usd": 100000,
            "exclude_keywords": [],
            "seniority": [],
            "greenhouse_companies": [],
        }
    )
    assert p.lever_companies == []
    assert p.ashby_companies == []
    assert p.workable_companies == []
    assert p.smartrecruiters_companies == []
