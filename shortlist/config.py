"""Configuration loading + validation for Shortlist."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    resume: Path
    output_dir: Path
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
