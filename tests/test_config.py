from src.common.config import PROJECT_ROOT, get_event_taxonomy, get_settings, get_tickers
from src.common.schemas import EventType


def test_project_root_contains_config():
    assert (PROJECT_ROOT / "config" / "settings.yaml").exists()


def test_settings_load():
    s = get_settings()
    assert s.signals.decay_half_life_hours > 0
    assert s.paths.signals_db.endswith(".db")


def test_taxonomy_covers_every_event_type():
    taxonomy = get_event_taxonomy()
    assert set(taxonomy) == set(EventType)
    assert all(1 <= cfg.base_severity <= 10 for cfg in taxonomy.values())


def test_tickers_load_and_are_unique():
    tickers = get_tickers()
    assert 15 <= len(tickers) <= 20
    assert all(t == cfg.ticker for t, cfg in tickers.items())
    assert all(cfg.aliases for cfg in tickers.values())
