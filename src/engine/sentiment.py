from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from src.common.config import get_settings
from src.engine.preprocessing import preprocess_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SentimentResult:
    score: float
    confidence: float
    method: str
    label: str


_POSITIVE = {
    "beat", "beats", "growth", "grew", "strong", "surge", "surges", "profit",
    "profitable", "upgrade", "upgraded", "record", "bullish", "gain", "gains",
    "rise", "rises", "rising", "approval", "approved", "success", "successful",
    "outperform", "outperformed", "positive", "recovery", "recover", "launch",
}
_NEGATIVE = {
    "loss", "losses", "decline", "declines", "declined", "drop", "drops", "dropped",
    "fall", "falls", "fell", "miss", "misses", "missed", "weak", "warning",
    "downgrade", "downgraded", "lawsuit", "fraud", "default", "bankruptcy", "crash",
    "crisis", "bearish", "negative", "recall", "outage", "layoffs", "layoff", "cuts",
}
_NEGATORS = {"not", "no", "never", "without", "hardly", "isn't", "wasn't", "won't", "failed"}
_TOKEN_RE = re.compile(r"\$?[A-Za-z]+(?:['’][A-Za-z]+)?")


class SentimentAnalyzer:
    """FinBERT sentiment inference with an explicit deterministic offline fallback.

    mode='auto' tries ProsusAI/finbert once, then falls back to a small lexicon if the
    package/model cannot be loaded. mode='finbert' raises instead of silently falling
    back. mode='lexicon' never downloads a model.
    """
    def __init__(self, mode: str = "auto", classifier: Any | None = None):
        if mode not in {"auto", "finbert", "lexicon"}:
            raise ValueError("mode must be auto, finbert, or lexicon")
        self.mode = mode
        self._classifier = classifier
        self._attempted = classifier is not None
        self._backend = "injected" if classifier is not None else None
        self._load_error: str | None = None

    def _load(self) -> Any:
        if self._classifier is not None:
            return self._classifier
        if self._attempted:
            if self._classifier is None and self.mode == "finbert":
                raise RuntimeError(f"FinBERT unavailable: {self._load_error}")
            return None
        self._attempted = True
        try:
            from transformers import pipeline
            model_name = get_settings().models.sentiment
            self._classifier = pipeline(
                "text-classification", model=model_name, tokenizer=model_name,
                top_k=None, truncation=True,
            )
            self._backend = "finbert"
            return self._classifier
        except Exception as exc:
            self._load_error = str(exc)
            if self.mode == "finbert":
                raise RuntimeError(f"Could not load FinBERT: {exc}") from exc
            logger.warning("FinBERT unavailable; using lexicon fallback (%s)", exc)
            return None

    @staticmethod
    def _parse_output(output: Any) -> tuple[dict[str, float], str]:
        if isinstance(output, list) and output and isinstance(output[0], list):
            output = output[0]
        if isinstance(output, dict):
            output = [output]
        probabilities: dict[str, float] = {}
        for item in output:
            label = str(item.get("label", "")).lower()
            score = float(item.get("score", 0.0))
            if "positive" in label:
                probabilities["positive"] = score
            elif "negative" in label:
                probabilities["negative"] = score
            elif "neutral" in label:
                probabilities["neutral"] = score
        if not probabilities:
            raise ValueError("Unrecognized FinBERT output labels")
        total = sum(probabilities.values())
        if total > 0:
            probabilities = {key: value / total for key, value in probabilities.items()}
        return probabilities, "finbert"

    def predict(self, text: str) -> SentimentResult:
        clean = preprocess_text(text)
        if not clean:
            return SentimentResult(0.0, 0.0, "empty", "neutral")
        classifier = None if self.mode == "lexicon" else self._load()
        if classifier is not None:
            output = classifier(clean[:4000])
            probabilities, method = self._parse_output(output)
            score = max(-1.0, min(1.0, probabilities.get("positive", 0.0) - probabilities.get("negative", 0.0)))
            confidence = max(probabilities.values()) if probabilities else 0.0
            label = "positive" if score > 0.12 else "negative" if score < -0.12 else "neutral"
            return SentimentResult(score, confidence, method, label)
        self._backend = "lexicon"
        return self._lexicon_predict(clean)

    @staticmethod
    def _lexicon_predict(text: str) -> SentimentResult:
        tokens = [token.lower().strip("'") for token in _TOKEN_RE.findall(text)]
        positive = negative = 0
        for index, token in enumerate(tokens):
            negated = any(word in _NEGATORS for word in tokens[max(0, index - 3):index])
            if token in _POSITIVE:
                if negated:
                    negative += 1
                else:
                    positive += 1
            elif token in _NEGATIVE:
                if negated:
                    positive += 1
                else:
                    negative += 1
        total = positive + negative
        if total == 0:
            return SentimentResult(0.0, 0.45, "lexicon", "neutral")
        score = max(-1.0, min(1.0, (positive - negative) / max(2.0, total ** 0.5 * 2)))
        confidence = min(0.85, 0.5 + 0.1 * total)
        label = "positive" if score > 0.12 else "negative" if score < -0.12 else "neutral"
        return SentimentResult(score, confidence, "lexicon", label)
