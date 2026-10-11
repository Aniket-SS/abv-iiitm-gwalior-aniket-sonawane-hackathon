from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from src.common.config import get_settings
from src.common.schemas import Document, EventType, Signal, make_signal_id, make_snippet
from src.engine.entity_linking import EntityLinkResult, link_entities
from src.engine.event_classifier import EventClassification, EventClassifier
from src.engine.impact import score_impact
from src.engine.preprocessing import preprocess_text
from src.engine.sentiment import SentimentAnalyzer, SentimentResult

logger = logging.getLogger(__name__)
MARKET_TICKER = "MARKET"


@dataclass
class RiskEngine:
    sentiment_mode: str = "auto"
    event_mode: str = "auto"
    use_spacy: bool = True

    def __post_init__(self) -> None:
        self.sentiment_analyzer = SentimentAnalyzer(self.sentiment_mode)
        self.event_classifier = EventClassifier(self.event_mode)

    def analyze_document(self, document: Document) -> list[Signal]:
        text = preprocess_text(" ".join(part for part in (document.title or "", document.text) if part))
        if not text:
            return []
        entities: EntityLinkResult = link_entities(text, use_spacy=self.use_spacy)
        sentiment: SentimentResult = self.sentiment_analyzer.predict(text)
        event: EventClassification = self.event_classifier.predict(text)
        impact = score_impact(text, event.event_type, sentiment.score, event.confidence)

        if entities.matches:
            targets = [(match.ticker, match.company, "company") for match in entities.matches]
        elif document.channel.value == "news":
            # Unlinked news can describe macroeconomic or geopolitical risk. Preserve
            # it for Module B without inventing a company ticker.
            targets = [(MARKET_TICKER, None, "market")]
        else:
            # Unlinked social posts are not automatically systemic-risk events.
            # Avoid turning ambiguous tweets into false market-wide signals.
            return []

        taxonomy_evidence = ", ".join(event.evidence) if event.evidence else "none"
        rationale = (
            f"sentiment={sentiment.method}:{sentiment.label} ({sentiment.score:+.2f}); "
            f"event={event.method}:{event.event_type.value} ({event.confidence:.2f}); "
            f"impact={impact.score:.1f} ({impact.rationale}); "
            f"entity_linking={entities.method}; keyword_evidence={taxonomy_evidence}"
        )
        confidence = max(0.0, min(1.0, (sentiment.confidence + event.confidence) / 2.0))
        signals: list[Signal] = []
        for ticker, company, scope in targets:
            signals.append(Signal(
                signal_id=make_signal_id(document.id, ticker),
                doc_id=document.id,
                timestamp=document.timestamp,
                source=document.source,
                channel=document.channel,
                ticker=ticker,
                scope=scope,
                company=company,
                sentiment=round(sentiment.score, 4),
                event_type=event.event_type,
                impact=impact.score,
                confidence=round(confidence, 4),
                rationale=rationale,
                text_snippet=make_snippet(text),
            ))
        return signals

    def run(self, documents: Iterable[Document]) -> list[Signal]:
        signals: list[Signal] = []
        for document in documents:
            try:
                signals.extend(self.analyze_document(document))
            except Exception:
                logger.exception("Could not analyze document id=%s source=%s", document.id, document.source)
        return signals


def run_pipeline(documents: Iterable[Document], sentiment_mode: str = "auto",
                 event_mode: str = "auto", use_spacy: bool = True) -> list[Signal]:
    return RiskEngine(sentiment_mode, event_mode, use_spacy).run(documents)
