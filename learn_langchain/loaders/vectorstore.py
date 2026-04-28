"""Persistent Chroma + fingerprint cache to skip re-embedding."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from learn_langchain.config import CHUNK_OVERLAP, CHUNK_SIZE, EMBEDDING_MODEL, PERSIST_DIR

if TYPE_CHECKING:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

COLLECTION = "resume"


def compute_fingerprint(
    resume_bytes: bytes,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model: str,
    override_employer: str,
    override_title: str,
) -> str:
    h = hashlib.sha256()
    h.update(resume_bytes)
    h.update(b"\0")
    h.update(str(chunk_size).encode())
    h.update(b"\0")
    h.update(str(chunk_overlap).encode())
    h.update(b"\0")
    h.update(embedding_model.encode())
    h.update(b"\0")
    h.update(override_employer.encode())
    h.update(b"\0")
    h.update(override_title.encode())
    return h.hexdigest()


def build_or_load_chroma(
    documents: list[Document],
    embeddings: GoogleGenerativeAIEmbeddings,
    fingerprint: str,
) -> Chroma:
    persist_dir = Path(PERSIST_DIR)
    fp_path = persist_dir / "fingerprint.json"

    record: dict[str, object] = {
        "fingerprint": fingerprint,
        "embedding_model": EMBEDDING_MODEL,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "collection": COLLECTION,
    }

    if fp_path.is_file():
        try:
            existing = json.loads(fp_path.read_text(encoding="utf-8"))
            if existing.get("fingerprint") == fingerprint:
                return Chroma(
                    persist_directory=str(persist_dir),
                    embedding_function=embeddings,
                    collection_name=COLLECTION,
                )
        except (json.JSONDecodeError, OSError):
            pass

    shutil.rmtree(persist_dir, ignore_errors=True)
    persist_dir.mkdir(parents=True, exist_ok=True)

    vs = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=str(persist_dir),
        collection_name=COLLECTION,
    )
    fp_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return vs
