"""Paths, chunk/embedding/LLM constants, env helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
RESUME_PATH = PROJECT_ROOT / "resume.md"
PERSIST_DIR = PROJECT_ROOT / ".chroma" / "resume"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

EMBEDDING_MODEL = "gemini-embedding-001"
LLM_MODEL = "gemini-2.5-flash-lite"


def load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    if not os.environ.get("GOOGLE_API_KEY"):
        for alt in ("GEMINI_API_KEY", "VITE_GEMINI_API_KEY"):
            if key := os.environ.get(alt):
                os.environ["GOOGLE_API_KEY"] = key
                break


def require_google_api_key() -> None:
    if not os.environ.get("GOOGLE_API_KEY"):
        raise EnvironmentError(
            "請設定環境變數 GOOGLE_API_KEY（Google AI Studio / Gemini API 金鑰）。"
        )


def override_fields() -> tuple[str, str]:
    employer = (os.environ.get("RESUME_EMPLOYER_OVERRIDE") or "").strip()
    title = (os.environ.get("RESUME_JOB_TITLE_OVERRIDE") or "").strip()
    return employer, title
