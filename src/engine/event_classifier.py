from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.common.config import EventTypeConfig, get_event_taxonomy, get_settings
from src.common.schemas import EventType
from src.engine.preprocessing import contains_term, preprocess_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventClassification:
    event_type: EventType
    confidence: float
    method: str
    evidence: tuple[str, ...] = ()


class EventClassifier:
    """Zero-shot event classifier, with a taxonomy-driven keyword fallback."""
    def __init__(self, mode: str = "auto", classifier: Any | None = None):
        if mode not in {"auto", "zero_shot", "rules"}:
            raise ValueError("mode must be auto, zero_shot, or rules")
        self.mode = mode
        self._classifier = classifier
        self._attempted = classifier is not None
        self._load_error: str | None = None

    def _load(self) -> Any | None:
        if self._classifier is not None:
            return self._classifier
        if self._attempted:
            if self.mode == "zero_shot":
                raise RuntimeError(f"Zero-shot model unavailable: {self._load_error}")
            return None
        self._attempted = True
        try:
            from transformers import pipeline
            model_name = get_settings().models.zero_shot
            self._classifier = pipeline("zero-shot-classification", model=model_name)
            return self._classifier
        except Exception as exc:
            self._load_error = str(exc)
            if self.mode == "zero_shot":
                raise RuntimeError(f"Could not load zero-shot classifier: {exc}") from exc
            logger.warning("Zero-shot model unavailable; using taxonomy keywords (%s)", exc)
            return None

    @staticmethod
    def _candidates() -> tuple[list[str], dict[str, EventType]]:
        taxonomy = get_event_taxonomy()
        labels: list[str] = []
        reverse: dict[str, EventType] = {}
        for event_type, cfg in taxonomy.items():
            labels.append(cfg.zero_shot_label)
            reverse[cfg.zero_shot_label] = event_type
        return labels, reverse

    def predict(self, text: str) -> EventClassification:
        clean = preprocess_text(text)
        taxonomy = get_event_taxonomy()
        classifier = None if self.mode == "rules" else self._load()
        if classifier is not None and clean:
            labels, reverse = self._candidates()
            result = classifier(clean[:4000], candidate_labels=labels, multi_label=False)
            label = str(result["labels"][0])
            scores = result.get("scores", [])
            event_type = reverse.get(label, EventType.OTHER)
            confidence = float(scores[0]) if scores else 0.5
            return EventClassification(event_type, max(0.0, min(1.0, confidence)), "zero_shot", ())
        return self._keyword_predict(clean, taxonomy)

    @staticmethod
    def _keyword_predict(text: str, taxonomy: dict[EventType, EventTypeConfig]) -> EventClassification:
        lowered = text.casefold()
        candidates: list[tuple[int, float, EventType, tuple[str, ...]]] = []
        for event_type, cfg in taxonomy.items():
            if event_type == EventType.OTHER:
                continue
            hits = tuple(keyword for keyword in cfg.keywords if contains_term(lowered, keyword))
            if hits:
                candidates.append((len(hits), cfg.base_severity, event_type, hits))
        if not candidates:
            return EventClassification(EventType.OTHER, 0.4, "taxonomy_keywords", ())
        hits, _, event_type, evidence = max(candidates, key=lambda row: (row[0], row[1]))
        confidence = min(0.9, 0.55 + 0.08 * (hits - 1))
        return EventClassification(event_type, confidence, "taxonomy_keywords", evidence[:5])
