"""GET /health and GET /api/health (matches frontend fetchHealth)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from memoir_rag.deps import get_rag_state
from memoir_rag.schemas.api import HealthResponse, health_response_from_rag
from memoir_rag.state import RagFailedState, RagReadyState

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
@router.get("/api/health", response_model=HealthResponse)
def health(
    rag: Annotated[RagReadyState | RagFailedState, Depends(get_rag_state)],
):
    return health_response_from_rag(rag)
