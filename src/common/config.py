"""Configuration loading.

* config/*.yaml  -> validated, typed objects (settings, tickers, event taxonomy)
* .env           -> secrets (API keys), read with get_env()

Import from anywhere in the project:
    from src.common.config import PROJECT_ROOT, get_settings, get_tickers, get_event_taxonomy
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.common.schemas import EventType

# src/common/config.py -> parents[0]=common, [1]=src, [2]=repository root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"

load_dotenv(PROJECT_ROOT / ".env")  # silently does nothing if .env doesn't exist


# ----------------------------------------------------------------------------- settings
class PathsConfig(BaseModel):
    data_raw: str = "data/raw"
    data_sample: str = "data/sample"
    data_processed: str = "data/processed"
    data_synthetic: str = "data/synthetic"
    signals_db: str = "data/processed/signals.db"


class ModelsConfig(BaseModel):
    sentiment: str = "ProsusAI/finbert"
    zero_shot: str = "facebook/bart-large-mnli"
    spacy: str = "en_core_web_sm"


class SignalsConfig(BaseModel):
    decay_half_life_hours: float = Field(default=48.0, gt=0)
    window_days: int = Field(default=7, gt=0)
    min_confidence: float = Field(default=0.5, ge=0, le=1)


class ApiConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000


class Settings(BaseModel):
    random_seed: int = 42
    log_level: str = "INFO"
    paths: PathsConfig = Field(default_factory=PathsConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    signals: SignalsConfig = Field(default_factory=SignalsConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)


# ----------------------------------------------------------------------------- tickers
class TickerConfig(BaseModel):
    ticker: str
    company: str
    sector: str
    aliases: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------------- events
class EventTypeConfig(BaseModel):
    label: str
    description: str = ""
    base_severity: float = Field(ge=1, le=10)
    zero_shot_label: str
    keywords: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------------- helpers
def _load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_path(relative: str | Path) -> Path:
    """Turn a repo-relative path from settings.yaml into an absolute path."""
    return PROJECT_ROOT / relative


def get_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    """Read a secret/env var. Use required=True to fail loudly when it's missing."""
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Environment variable {name} is not set. Add it to your .env file.")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.model_validate(_load_yaml("settings.yaml"))


@lru_cache(maxsize=1)
def get_tickers() -> dict[str, TickerConfig]:
    """Ticker symbol -> TickerConfig. Fails on duplicate tickers."""
    raw = _load_yaml("tickers.yaml").get("tickers", [])
    result: dict[str, TickerConfig] = {}
    for item in raw:
        cfg = TickerConfig.model_validate(item)
        if cfg.ticker in result:
            raise ValueError(f"Duplicate ticker in tickers.yaml: {cfg.ticker}")
        result[cfg.ticker] = cfg
    return result


@lru_cache(maxsize=1)
def get_event_taxonomy() -> dict[EventType, EventTypeConfig]:
    """EventType -> EventTypeConfig. Fails if the YAML and the enum disagree."""
    raw = _load_yaml("event_taxonomy.yaml").get("events", {})
    yaml_keys = set(raw)
    enum_keys = {e.value for e in EventType}
    if yaml_keys != enum_keys:
        raise ValueError(
            "event_taxonomy.yaml and EventType enum are out of sync. "
            f"Missing in YAML: {sorted(enum_keys - yaml_keys)}; "
            f"unknown in YAML: {sorted(yaml_keys - enum_keys)}"
        )
    return {EventType(k): EventTypeConfig.model_validate(v) for k, v in raw.items()}
