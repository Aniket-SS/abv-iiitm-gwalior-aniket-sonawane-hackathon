"""Entity-linking rules: case-sensitive where a name/symbol is also an everyday word."""
import pytest

from src.ingestion.normalization import entity_metadata, link_tickers


def linked(text: str) -> set[str]:
    return {m["ticker"] for m in link_tickers(text)}


# ----- must NOT link (false-positive traps) ----------------------------------------------
@pytest.mark.parametrize("text", [
    "",
    "Cost of living keeps rising, central bank warns",
    "COST OF LIVING CRISIS DEEPENS",                    # all-caps headline, no exchange prefix
    "I ate an apple and read a meta-analysis on inflation",
    "Meta-analysis shows modest gains",
    "Apple pie recipe goes viral",
    "intel from the field says the ceasefire holds",
    "PG-13 movie night, KO in round two",
    "Dis is a good thing; ba da bing",
    "Amazon river flooding disrupts shipping",
    "The Amazon rainforest is shrinking",
    "CRM software market keeps growing",
    "coke oven fire reported at the steel plant",
    "apple stock jumps",                                # lowercase ambiguous name: conservative miss
    "Fed raises rates and warns on inflation",
    "Stocks rise as markets await jobs data",
])
def test_no_false_links(text):
    assert linked(text) == set()


# ----- must link --------------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("Apple Inc. shares rise", {"AAPL"}),
    ("Apple unveils new iPhone", {"AAPL"}),
    ("Meta shares fall after earnings miss", {"META"}),
    ("Facebook parent reports results", {"META"}),
    ("Intel reports suggest talks stalled", {"INTC"}),
    ("Amazon expands AWS capacity", {"AMZN"}),
    ("Coke recalls bottles", {"KO"}),
    ("Coca-Cola raises prices", {"KO"}),
    ("$AAPL and $tsla rally", {"AAPL", "TSLA"}),
    ("$COST hits a record high", {"COST"}),
    ("$CRM breaks out", {"CRM"}),
    ("Costco raises membership fee", {"COST"}),
    ("(NASDAQ: COST) reported sales", {"COST"}),
    ("NYSE: KO said on Tuesday", {"KO"}),
    ("NYSE: PG raised its forecast", {"PG"}),
    ("AMD results strong", {"AMD"}),
    ("Fed raises rates; Boeing grounds 737 fleet", {"BA"}),
    ("tesla and MICROSOFT both fall", {"TSLA", "MSFT"}),
    ("Salesforce beats estimates", {"CRM"}),
    ("Alphabet Inc. results", {"GOOG"}),
    ("Google faces new antitrust suit", {"GOOG"}),
    ("Procter & Gamble lifts outlook", {"PG"}),
    ("P&G raises prices", {"PG"}),
    ("Verizon adds subscribers", {"VZ"}),
    ("Netflix password crackdown pays off", {"NFLX"}),
    ("Disney+ price hike", {"DIS"}),
    ("Intel and AMD fight for share", {"INTC", "AMD"}),
])
def test_true_links(text, expected):
    assert linked(text) == expected


def test_every_configured_ticker_is_linkable_by_cashtag_and_company_name():
    from src.common.config import get_tickers
    for ticker, cfg in get_tickers().items():
        assert linked(f"${ticker} moves") == {ticker}
        assert ticker in linked(f"{cfg.company} said today"), ticker


def test_match_kind_is_reported():
    kinds = {m["ticker"]: m["match"] for m in link_tickers("$AAPL, AMD and Tesla")}
    assert kinds == {"AAPL": "cashtag", "AMD": "symbol", "TSLA": "name"}


def test_entity_metadata_scope_follows_linking():
    assert entity_metadata("Cost of living rises")["entity_scope"] == "market"
    assert entity_metadata("Tesla recalls cars")["tickers"] == ["TSLA"]
