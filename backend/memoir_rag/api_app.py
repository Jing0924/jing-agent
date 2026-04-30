"""FastAPI app for resume RAG: chain built once at startup.

Run the API (dev)，於 `backend/` 目錄下：

  cd backend && uvicorn memoir_rag.api_app:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from memoir_rag.chains.resume_rag import build_resume_rag_chain
from memoir_rag.config import cors_allow_origins, load_env, resolve_knowledge_md_paths
from memoir_rag.middleware.request_log import RequestLoggingMiddleware
from memoir_rag.routers import ask, calendar, health
from memoir_rag.state import RagFailedState, RagReadyState

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        load_env()
        bundle = build_resume_rag_chain()
        app.state.rag = RagReadyState(
            chain=bundle.chain,
            embedding_fingerprint=bundle.embedding_fingerprint,
            prompt_sha256=bundle.prompt_sha256,
            llm_model=bundle.llm_model,
        )
        sources = resolve_knowledge_md_paths()
        logger.info("Resume RAG chain loaded from %s", [str(p) for p in sources])
    except Exception as e:
        app.state.rag = RagFailedState(error=str(e))
        logger.exception("Failed to build resume RAG chain: %s", e)
    yield


app = FastAPI(title="Resume RAG API", lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ask.router)
app.include_router(calendar.router)
