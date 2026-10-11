from __future__ import annotations

import html
import re
import unicodedata

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


def preprocess_text(text: str | None) -> str:
    """Normalize markup and whitespace without deleting finance-relevant tokens.

    Numbers, negations, cashtags, tickers, currency signs, and punctuation are
    intentionally retained because they can change the meaning of financial news.
    """
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", html.unescape(str(text)))
    value = _HTML_TAG_RE.sub(" ", value)
    value = _URL_RE.sub(" URL ", value)
    value = value.replace("\x00", " ")
    return _SPACE_RE.sub(" ", value).strip()


def contains_term(text: str, term: str) -> bool:
    """Case-insensitive phrase match with token boundaries (avoids 'war' in 'warn')."""
    phrase = re.escape(" ".join(term.split())).replace(r"\ ", r"\s+")
    return re.search(rf"(?<!\w){phrase}(?!\w)", text, flags=re.IGNORECASE) is not None
