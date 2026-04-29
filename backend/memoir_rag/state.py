"""Application RAG state attached to ``app.state.rag`` after lifespan startup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RagReadyState:
    chain: Any
    embedding_fingerprint: str
    prompt_sha256: str
    llm_model: str


@dataclass(frozen=True)
class RagFailedState:
    error: str
