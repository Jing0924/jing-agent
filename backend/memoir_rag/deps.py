"""FastAPI dependency helpers."""

from __future__ import annotations

from fastapi import HTTPException, Request

from memoir_rag.state import RagFailedState, RagReadyState


def get_rag_state(request: Request) -> RagReadyState | RagFailedState:
    rag = getattr(request.app.state, "rag", None)
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="Application state not initialized.",
        )
    return rag


def get_ready_rag(request: Request) -> RagReadyState:
    rag = get_rag_state(request)
    if isinstance(rag, RagFailedState):
        raise HTTPException(status_code=503, detail=rag.error)
    return rag
