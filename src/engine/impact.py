from __future__ import annotations

from dataclasses import dataclass

from src.common.config import get_event_taxonomy
from src.common.schemas import EventType
from src.engine.preprocessing import contains_term, preprocess_text


@dataclass(frozen=True)
class ImpactResult:
    score: float
    rationale: str
    evidence: tuple[str, ...]


_HIGH_SEVERITY_TERMS = (
    "bankruptcy", "default", "bankrupt", "war", "invasion", "sanctions", "emergency",
    "recall", "cyberattack", "data breach", "shutdown", "fraud", "insolvency",
    "massive loss", "profit warning", "halted trading", "credit downgrade",
)
_MEDIUM_SEVERITY_TERMS = (
    "lawsuit", "investigation", "fine", "strike", "outage", "resign", "resignation",
    "missed estimates", "cuts guidance", "rate hike", "tariff", "layoffs", "downgrade",
)


def score_impact(text: str, event_type: EventType, sentiment: float = 0.0,
                 event_confidence: float = 0.5) -> ImpactResult:
    """Rule-based 1–10 event severity estimate; not a calibrated market-loss forecast."""
    clean = preprocess_text(text)
    lowered = clean.casefold()
    base = float(get_event_taxonomy()[event_type].base_severity)
    evidence = [term for term in _HIGH_SEVERITY_TERMS if contains_term(lowered, term)]
    medium = [term for term in _MEDIUM_SEVERITY_TERMS if contains_term(lowered, term)]
    score = base
    if evidence:
        score += 1.5
    elif medium:
        score += 0.75
    if abs(sentiment) >= 0.65:
        score += 0.5
    if event_confidence >= 0.85:
        score += 0.25
    score = round(max(1.0, min(10.0, score)), 2)
    reasons = [f"{event_type.value} base severity={base:g}"]
    if evidence:
        reasons.append("high-severity terms: " + ", ".join(evidence[:3]))
    elif medium:
        reasons.append("severity terms: " + ", ".join(medium[:3]))
    if abs(sentiment) >= 0.65:
        reasons.append("strong sentiment magnitude")
    if event_confidence >= 0.85:
        reasons.append("high event-classification confidence")
    return ImpactResult(score, "; ".join(reasons), tuple((evidence or medium)[:5]))
