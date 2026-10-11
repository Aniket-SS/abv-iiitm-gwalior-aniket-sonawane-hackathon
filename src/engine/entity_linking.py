from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.common.config import get_tickers, get_settings
from src.ingestion.normalization import link_tickers
from src.engine.preprocessing import preprocess_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntityMatch:
    ticker: str
    company: str
    evidence: str


@dataclass(frozen=True)
class EntityLinkResult:
    matches: tuple[EntityMatch, ...]
    named_entities: tuple[tuple[str, str], ...]
    method: str

    @property
    def tickers(self) -> list[str]:
        return [match.ticker for match in self.matches]


@lru_cache(maxsize=1)
def _load_spacy_model() -> Any | None:
    try:
        import spacy
        model_name = get_settings().models.spacy
        return spacy.load(model_name)
    except Exception as exc:
        logger.warning("spaCy NER unavailable; alias matching remains active (%s)", exc)
        return None


def link_entities(text: str, use_spacy: bool = True) -> EntityLinkResult:
    """Link only configured companies; never infer a ticker from general context.

    The existing case-sensitive whole-word alias matcher is the authority for ticker
    assignment. spaCy NER adds entity evidence for diagnostics and rationale but cannot
    override ambiguous-name safeguards such as Apple, Meta, Amazon, or Intel.
    """
    clean = preprocess_text(text)
    if not clean:
        return EntityLinkResult((), (), "none")

    linked = link_tickers(clean)
    matches = tuple(
        EntityMatch(ticker=item["ticker"], company=item["company"], evidence=item["match"])
        for item in linked
    )
    named_entities: list[tuple[str, str]] = []
    method = "alias_dictionary"
    if use_spacy:
        nlp = _load_spacy_model()
        if nlp is not None:
            try:
                doc = nlp(clean[:100_000])
                named_entities = [(ent.text, ent.label_) for ent in doc.ents]
                method = "spacy+alias_dictionary"
            except Exception as exc:
                logger.warning("spaCy inference failed; using alias dictionary (%s)", exc)

    return EntityLinkResult(matches, tuple(named_entities), method)
