"""Configuration loading + validation for Shortlist."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from shortlist import places

DEFAULT_CONFIG_YAML = """\
# Shortlist configuration. See docs/spec.md for the full reference.
anthropic:
  key_source: env
  key_env_var: ANTHROPIC_API_KEY
budget:
  daily_usd: 5.00
  monthly_usd: 60.00
paths:
  pdf_template: ~/.config/shortlist/pdf-template.tex
sources:
  greenhouse:
    enabled: true
    rate_limit_rpm: 30
  indeed:
    enabled: false
    rate_limit_rpm: 6
  linkedin:
    enabled: false
    rate_limit_rpm: 4
  glassdoor:
    enabled: false
    rate_limit_rpm: 6
  hn_who_hiring:
    enabled: true
  remoteok:
    enabled: true
  wellfound:
    enabled: false
    rate_limit_rpm: 6
  otta:
    enabled: false
    rate_limit_rpm: 6
  rss:
    enabled: true
ranker:
  top_k_for_llm_rerank: 30
  embedding_model: BAAI/bge-small-en-v1.5
  rerank_model: claude-haiku-4-5-20251001
tailor:
  model: claude-sonnet-4-6
  cover_paragraphs: 3
"""

DEFAULT_PREFS_YAML = """\
# Shortlist preferences. Edit these to taste.
titles:
  - "Senior Backend Engineer"
  - "Staff Engineer"
locations:
  - "Remote - US"
  - "Atlanta, GA"
remote_ok: true
comp_floor_usd: 180000
exclude_keywords: []
seniority:
  - senior
  - staff
greenhouse_companies: []
lever_companies: []
ashby_companies: []
workable_companies: []
smartrecruiters_companies: []
indeed_queries: []
linkedin_queries: []
glassdoor_queries: []
hn_enabled: false
remoteok_enabled: false
wellfound_queries: []
otta_queries: []
rss_urls: []
"""


class AnthropicConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key_source: Literal["env", "keyring"] = "env"
    key_env_var: str = "ANTHROPIC_API_KEY"


class BudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_usd: float = Field(ge=0)
    monthly_usd: float = Field(ge=0)


class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Legacy and unused: per-person resume/output paths now come from the
    # active Profile (shortlist.profiles.Profile.resume_path/output_dir).
    # Kept optional, not deleted, so an existing config.yaml with these keys
    # still loads.
    resume: Path | None = None
    # Legacy and unused: see `resume` above; output now comes from
    # Profile.output_dir.
    output_dir: Path | None = None
    pdf_template: Path | None = None


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    rate_limit_rpm: int = Field(default=30, ge=1)
    urls: list[str] = Field(default_factory=list)  # for RSS


class RankerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    top_k_for_llm_rerank: int = Field(default=30, ge=1)
    embedding_model: str
    rerank_model: str


class TailorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    cover_paragraphs: int = Field(default=3, ge=1, le=10)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anthropic: AnthropicConfig
    budget: BudgetConfig
    paths: PathsConfig
    sources: dict[str, SourceConfig]
    ranker: RankerConfig
    tailor: TailorConfig


class Prefs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titles: list[str] = Field(min_length=1)
    locations: list[str]
    remote_ok: bool
    comp_floor_usd: int = Field(ge=0)
    exclude_keywords: list[str]
    seniority: list[str]
    greenhouse_companies: list[str] = Field(default_factory=list)
    lever_companies: list[str] = Field(default_factory=list)
    ashby_companies: list[str] = Field(default_factory=list)
    workable_companies: list[str] = Field(default_factory=list)
    smartrecruiters_companies: list[str] = Field(default_factory=list)
    indeed_queries: list[str] = Field(default_factory=list)
    linkedin_queries: list[str] = Field(default_factory=list)
    glassdoor_queries: list[str] = Field(default_factory=list)
    hn_enabled: bool = False
    remoteok_enabled: bool = False
    remotive_enabled: bool = False
    wellfound_queries: list[str] = Field(default_factory=list)
    otta_queries: list[str] = Field(default_factory=list)
    rss_urls: list[str] = Field(default_factory=list)
    # Where Indeed, LinkedIn and Glassdoor search. Unlike `locations` (a
    # substring filter on fetched jobs), each entry must be a known place.
    search_locations: list[str] = Field(default_factory=list)

    @field_validator("search_locations")
    @classmethod
    def _known_places(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in v:
            if not raw.strip():
                continue
            name = places.canonical(raw)
            if name is None:
                raise ValueError(f"not a known place: {raw.strip()!r}")
            out.append(name)
        return out

    @field_validator(
        "titles",
        "locations",
        "exclude_keywords",
        "seniority",
        "greenhouse_companies",
        "lever_companies",
        "ashby_companies",
        "workable_companies",
        "smartrecruiters_companies",
        "indeed_queries",
        "linkedin_queries",
        "glassdoor_queries",
        "wellfound_queries",
        "otta_queries",
        "rss_urls",
    )
    @classmethod
    def _strip(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s.strip()]


def load_config(path: Path) -> Config:
    with path.expanduser().open() as f:
        data = yaml.safe_load(f)
    return Config.model_validate(data)


def load_prefs(path: Path) -> Prefs:
    with path.expanduser().open() as f:
        data = yaml.safe_load(f)
    return Prefs.model_validate(data)
