"""HTTP request/response models for the public API surface."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator

from memoir_rag.config import speech_enabled
from memoir_rag.state import RagFailedState, RagReadyState


class HealthResponse(BaseModel):
    status: str
    ready: bool
    error: str | None = None
    embedding_fingerprint: str | None = None
    prompt_sha256: str | None = None
    llm_model: str | None = None
    speech_enabled: bool = False


def health_response_from_rag(rag: RagReadyState | RagFailedState) -> HealthResponse:
    se = speech_enabled()
    if isinstance(rag, RagFailedState):
        return HealthResponse(
            status="degraded",
            ready=False,
            error=rag.error,
            speech_enabled=se,
        )
    return HealthResponse(
        status="ok",
        ready=True,
        error=None,
        embedding_fingerprint=rag.embedding_fingerprint,
        prompt_sha256=rag.prompt_sha256,
        llm_model=rag.llm_model,
        speech_enabled=se,
    )


class AskBody(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def question_non_empty_after_strip(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Question cannot be empty.")
        return s


class AskResponse(BaseModel):
    answer: str = ""

    @classmethod
    def from_chain_result(cls, result: dict[str, Any]) -> AskResponse:
        answer = result.get("answer", "")
        if not isinstance(answer, str):
            answer = str(answer)
        return cls(answer=answer)
