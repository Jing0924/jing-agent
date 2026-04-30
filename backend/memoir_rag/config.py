"""Paths, chunk/embedding/LLM constants, env helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent

# `knowledge/` 下所有 `.md`（含子目錄）若存在至少一個，則優先使用；否則退回應用程式根（`PROJECT_ROOT`）底下的單檔 `resume.md`。
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
RESUME_PATH = PROJECT_ROOT / "resume.md"
PERSIST_DIR = PROJECT_ROOT / ".chroma" / "resume"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

EMBEDDING_MODEL = "gemini-embedding-001"
LLM_MODEL = "gemini-2.5-flash-lite"


def load_env() -> None:
    repo_root = PROJECT_ROOT.parent
    load_dotenv(repo_root / ".env")
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


def cors_allow_origins() -> list[str]:
    """Comma-separated origins from MEMOIR_CORS_ORIGINS or CORS_ALLOW_ORIGINS; default local Vite."""
    raw = (os.environ.get("MEMOIR_CORS_ORIGINS") or os.environ.get("CORS_ALLOW_ORIGINS") or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def resolve_knowledge_md_paths() -> list[Path]:
    """要向量化之 Markdown 路徑（穩定排序）。"""
    if KNOWLEDGE_DIR.is_dir():
        md_files = sorted(KNOWLEDGE_DIR.rglob("*.md"), key=lambda p: p.as_posix())
        if md_files:
            return md_files
    if RESUME_PATH.is_file():
        return [RESUME_PATH]
    raise FileNotFoundError(
        f"找不到知識庫：請在 `{KNOWLEDGE_DIR.name}/` 下至少放入一個 `.md`（可在子目錄），"
        f"或使用 {RESUME_PATH}（與 `{KNOWLEDGE_DIR.name}` 同屬應用程式根）。"
    )


def knowledge_fingerprint_bytes(paths: list[Path]) -> bytes:
    """將相對路徑與檔案內容合併，任一档變更即改變嵌入指紋。"""
    root = PROJECT_ROOT.resolve()
    parts: list[bytes] = []
    for p in sorted(paths, key=lambda x: x.resolve().relative_to(root).as_posix()):
        rel = str(p.resolve().relative_to(root)).encode()
        parts.append(rel + b"\0")
        parts.append(p.read_bytes())
        parts.append(b"\n")
    return b"".join(parts)
