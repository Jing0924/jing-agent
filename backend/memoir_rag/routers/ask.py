"""POST /api/ask and POST /api/ask/stream."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from memoir_rag.chains.resume_rag import iter_answer_stream_deltas
from memoir_rag.deps import get_ready_rag
from memoir_rag.schemas.api import AskBody, AskResponse
from memoir_rag.state import RagReadyState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ask"])


@router.post("/api/ask", response_model=AskResponse)
def ask(
    body: AskBody,
    rag: Annotated[RagReadyState, Depends(get_ready_rag)],
):
    try:
        result = rag.chain.invoke({"input": body.question})
        if not isinstance(result, dict):
            result = {}
        return AskResponse.from_chain_result(result)
    except Exception as e:
        logger.exception("Chain invoke failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate an answer. Please try again later.",
        ) from e


def _sse_event(event: str, data_obj: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data_obj, ensure_ascii=False)}\n\n"


@router.post("/api/ask/stream")
def ask_stream(
    body: AskBody,
    rag: Annotated[RagReadyState, Depends(get_ready_rag)],
):
    """SSE: `meta` (fingerprints), then `token` with JSON `{"text": "..."}` per chunk."""

    def generate():
        yield _sse_event(
            "meta",
            {
                "embeddingFingerprint": rag.embedding_fingerprint,
                "promptSha256": rag.prompt_sha256,
                "llmModel": rag.llm_model,
            },
        )
        try:
            for delta in iter_answer_stream_deltas(rag.chain, {"input": body.question}):
                if delta:
                    yield _sse_event("token", {"text": delta})
        except Exception as e:
            logger.exception("Chain stream failed: %s", e)
            yield _sse_event(
                "error",
                {"message": "Failed to generate an answer. Please try again later."},
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
