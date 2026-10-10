from src.common.config import PROJECT_ROOT, get_event_taxonomy, get_settings, get_tickers
from src.common.schemas import EventType


EXPECTED_TICKERS = {
    "AAPL", "AMD", "AMZN", "BA", "COST", "CRM", "DIS", "GOOG",
    "INTC", "KO", "META", "MSFT", "NFLX", "PG", "TSLA", "VZ",
}


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


def test_tickers_load_and_match_approved_universe():
    tickers = get_tickers()
    assert set(tickers) == EXPECTED_TICKERS
    assert len(tickers) == len(EXPECTED_TICKERS)
    assert all(ticker == cfg.ticker for ticker, cfg in tickers.items())
    assert all(cfg.aliases for cfg in tickers.values())
