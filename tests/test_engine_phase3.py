from datetime import datetime, timezone

from src.common.schemas import Channel, Document, EventType, Signal, make_signal_id
from src.engine.entity_linking import link_entities
from src.engine.event_classifier import EventClassifier
from src.engine.impact import score_impact
from src.engine.pipeline import MARKET_TICKER, RiskEngine
from src.engine.preprocessing import preprocess_text
from src.engine.sentiment import SentimentAnalyzer


def _doc(text: str, doc_id: str = "phase3-test") -> Document:
    return Document(
        id=doc_id,
        source="synthetic_test",
        channel=Channel.NEWS,
        timestamp=datetime(2026, 10, 10, tzinfo=timezone.utc),
        text=text,
        raw_meta={"synthetic": True},
    )


def test_preprocessing_removes_markup_and_normalizes_spaces():
    assert preprocess_text(" <b>Loss</b>  reported https://example.com/a ") == "Loss reported URL"


def test_entity_linking_matches_configured_ticker_and_preserves_case_safeguards():
    assert "AAPL" in link_entities("$AAPL revenue rises", use_spacy=False).tickers
    assert "AAPL" not in link_entities("I ate an apple pie", use_spacy=False).tickers
    assert "META" not in link_entities("meta-analysis of markets", use_spacy=False).tickers


def test_lexicon_sentiment_bounds_and_direction():
    analyzer = SentimentAnalyzer(mode="lexicon")
    positive = analyzer.predict("The company reports strong growth and record profit")
    negative = analyzer.predict("The company warns of losses and bankruptcy")
    assert 0 < positive.score <= 1
    assert -1 <= negative.score < 0
    assert 0 <= positive.confidence <= 1


def test_keyword_event_classifier_and_impact_threshold():
    text = "War and sanctions create a geopolitical crisis for shipping routes"
    result = EventClassifier(mode="rules").predict(text)
    impact = score_impact(text, result.event_type, sentiment=-0.8, event_confidence=result.confidence)
    assert result.event_type == EventType.GEOPOLITICAL
    assert impact.score > 7


def test_pipeline_emits_ticker_signal_and_deterministic_id():
    engine = RiskEngine(sentiment_mode="lexicon", event_mode="rules", use_spacy=False)
    signals = engine.analyze_document(_doc("$TSLA warns of delivery decline and losses", "doc-tsla"))
    assert len(signals) == 1
    signal = signals[0]
    assert isinstance(signal, Signal)
    assert signal.ticker == "TSLA"
    assert signal.scope == "company"
    assert signal.signal_id == make_signal_id("doc-tsla", "TSLA")
    assert len(signal.text_snippet) <= 300


def test_unlinked_event_uses_market_sentinel_for_required_ticker_contract():
    engine = RiskEngine(sentiment_mode="lexicon", event_mode="rules", use_spacy=False)
    signals = engine.analyze_document(_doc("War and sanctions disrupt shipping routes", "doc-market"))
    assert len(signals) == 1
    assert signals[0].ticker == MARKET_TICKER
    assert signals[0].scope == "market"
    assert signals[0].company is None
    assert signals[0].event_type == EventType.GEOPOLITICAL


def test_pipeline_handles_multiple_configured_entities():
    engine = RiskEngine(sentiment_mode="lexicon", event_mode="rules", use_spacy=False)
    signals = engine.analyze_document(_doc("$AAPL and $MSFT report strong growth", "doc-multi"))
    assert {signal.ticker for signal in signals} == {"AAPL", "MSFT"}


def test_word_boundaries_prevent_false_geopolitical_match_in_warns():
    result = EventClassifier(mode="rules").predict("Tesla warns of delivery declines and losses")
    assert result.event_type != EventType.GEOPOLITICAL
    impact = score_impact("Tesla warns of delivery declines and losses", result.event_type, -0.7, result.confidence)
    assert impact.score < 8


def test_finbert_output_uses_named_labels_not_numeric_label_assumptions():
    analyzer = SentimentAnalyzer(mode="finbert", classifier=lambda text: [
        {"label": "positive", "score": 0.7},
        {"label": "negative", "score": 0.1},
        {"label": "neutral", "score": 0.2},
    ])
    result = analyzer.predict("Synthetic test text")
    assert result.score > 0.5
    assert result.label == "positive"


def test_zero_shot_classifier_maps_taxonomy_label_to_event_type():
    from src.common.config import get_event_taxonomy

    label = get_event_taxonomy()[EventType.CREDIT_EVENT].zero_shot_label
    classifier = lambda text, candidate_labels, multi_label: {
        "labels": [label, *[item for item in candidate_labels if item != label]],
        "scores": [0.91, *([0.01] * (len(candidate_labels) - 1))],
    }
    result = EventClassifier(mode="zero_shot", classifier=classifier).predict("A borrower defaults")
    assert result.event_type == EventType.CREDIT_EVENT
    assert result.confidence == 0.91


def test_signal_scope_defaults_to_company_for_backwards_compatibility():
    from datetime import datetime, timezone
    from src.common.schemas import Channel, EventType, Signal

    signal = Signal(
        signal_id="legacy-signal", doc_id="legacy-doc",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="legacy", channel=Channel.SOCIAL, ticker="AAPL",
        sentiment=0.1, event_type=EventType.OTHER, impact=2, confidence=0.8,
    )
    assert signal.scope == "company"


def test_unlinked_social_post_does_not_become_market_signal():
    engine = RiskEngine(sentiment_mode="lexicon", event_mode="rules", use_spacy=False)
    doc = Document(
        id="unlinked-tweet", source="stock_tweets", channel=Channel.SOCIAL,
        timestamp=datetime(2026, 10, 10, tzinfo=timezone.utc),
        text="Markets feel uncertain today", raw_meta={"entity_scope": "unlinked"},
    )
    assert engine.analyze_document(doc) == []
