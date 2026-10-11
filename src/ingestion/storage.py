from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from src.common.schemas import Document
from src.ingestion.normalization import deduplicate


def write_jsonl(documents: Iterable[Document], path: str | Path, dedupe: bool = True) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    docs = deduplicate(documents) if dedupe else list(documents)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for doc in docs:
            handle.write(doc.model_dump_json() + "\n")
    return len(docs)


def read_jsonl(path: str | Path) -> list[Document]:
    path = Path(path)
    if not path.exists():
        return []
    documents: list[Document] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                documents.append(Document.model_validate_json(line))
            except ValidationError as exc:
                raise ValueError(f"Invalid Document JSON at {path}:{line_no}: {exc}") from exc
    return documents


def merge_jsonl(inputs: list[str | Path], output: str | Path) -> int:
    docs: list[Document] = []
    for path in inputs:
        docs.extend(read_jsonl(path))
    return write_jsonl(docs, output, dedupe=True)
