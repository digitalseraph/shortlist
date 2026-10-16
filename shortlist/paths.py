"""Resolve shortlist paths.

Honors env overrides (used by tests):
  SHORTLIST_CONFIG_HOME → config_dir()
  SHORTLIST_DATA_HOME   → data_dir()
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

_APP = "shortlist"


def config_dir() -> Path:
    env = os.environ.get("SHORTLIST_CONFIG_HOME")
    if env:
        return Path(env)
    return Path(user_config_dir(_APP))


def data_dir() -> Path:
    env = os.environ.get("SHORTLIST_DATA_HOME")
    if env:
        return Path(env)
    return Path(user_data_dir(_APP))


def config_path() -> Path:
    return config_dir() / "config.yaml"
