"""Ingestion-time authoritative Documents (header + optional current employment)."""

from __future__ import annotations

import re

from langchain_core.documents import Document

from learn_langchain.loaders.resume import _clean_resume_text


def build_authoritative_documents(
    resume_text: str, employer: str, title: str
) -> list[Document]:
    """Header (before first ---) plus optional positive current-employment facts from overrides."""
    text = _clean_resume_text(resume_text)
    docs: list[Document] = []

    parts = re.split(r"\n---\s*\n", text, maxsplit=1)
    header = parts[0].strip()
    if header:
        body = "【履歷開頭基本資料】\n" + header
        docs.append(
            Document(
                page_content=body,
                metadata={
                    "source": "resume",
                    "kind": "header",
                    "authoritative": True,
                    "priority": 10,
                },
            )
        )

    if employer or title:
        lines = [
            "【已校正之最新任職資訊】",
            f"雇主全名：{employer}" if employer else "",
            f"目前職稱：{title}" if title else "",
            "本段為履歷已確認之最新事實，描述目前工作時請以本段為準。",
        ]
        body = "\n".join(line for line in lines if line)
        docs.append(
            Document(
                page_content=body,
                metadata={
                    "source": "resume_override",
                    "kind": "current_employment",
                    "authoritative": True,
                    "priority": 0,
                },
            )
        )

    return docs


def tag_body_chunks(chunks: list[Document]) -> list[Document]:
    out: list[Document] = []
    for d in chunks:
        meta = dict(d.metadata)
        meta["source"] = "resume_body"
        meta["authoritative"] = False
        meta["priority"] = 100
        out.append(Document(page_content=d.page_content, metadata=meta))
    return out
