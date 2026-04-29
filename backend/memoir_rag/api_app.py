"""FastAPI app for resume RAG: chain built once at startup.

Run the API (dev):

  uvicorn learn_langchain.api_app:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from learn_langchain.chains.resume_rag import build_resume_rag_chain
from learn_langchain.config import RESUME_PATH, load_env

logger = logging.getLogger(__name__)

_chain: Any | None = None
_chain_error: str | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _chain, _chain_error
    _chain = None
    _chain_error = None
    load_env()
    try:
        _chain = build_resume_rag_chain(RESUME_PATH)
        logger.info("Resume RAG chain loaded from %s", RESUME_PATH)
    except Exception as e:
        _chain_error = str(e)
        logger.exception("Failed to build resume RAG chain: %s", e)
    yield


app = FastAPI(title="Resume RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


def _health_payload() -> dict[str, Any]:
    ready = _chain is not None and _chain_error is None
    return {
        "status": "ok" if ready else "degraded",
        "ready": ready,
        "error": _chain_error,
    }


@app.get("/health")
@app.get("/api/health")
def health():
    return _health_payload()


@app.post("/api/ask")
def ask(body: AskBody):
    if _chain is None:
        raise HTTPException(
            status_code=503,
            detail=_chain_error or "Resume RAG chain is not available.",
        )

    try:
        result = _chain.invoke({"input": body.question})
        answer = result.get("answer", "")
        if not isinstance(answer, str):
            answer = str(answer)
        return {"answer": answer}
    except Exception as e:
        logger.exception("Chain invoke failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate an answer. Please try again later.",
        ) from e
