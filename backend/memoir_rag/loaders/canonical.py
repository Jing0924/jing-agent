"""Ingestion-time authoritative Documents (header + optional current employment)."""

from __future__ import annotations

import re

from langchain_core.documents import Document

from memoir_rag.loaders.resume import _clean_resume_text


def build_authoritative_documents(
    resume_text: str,
    employer: str,
    title: str,
    *,
    include_employment_override: bool = True,
    header_stem: str | None = None,
) -> list[Document]:
    """Header (before first ---) plus optional current-employment facts from overrides."""
    text = _clean_resume_text(resume_text)
    docs: list[Document] = []

    parts = re.split(r"\n---\s*\n", text, maxsplit=1)
    header = parts[0].strip()
    if header:
        banner = (
            f"履歷開頭基本資料 · {header_stem}"
            if header_stem
            else "履歷開頭基本資料"
        )
        body = f"【{banner}】\n" + header
        hdr_meta: dict[str, str | bool | int] = {
            "source": "resume",
            "kind": "header",
            "authoritative": True,
            "priority": 10,
        }
        if header_stem:
            hdr_meta["knowledge_file"] = f"{header_stem}.md"
        docs.append(Document(page_content=body, metadata=hdr_meta))

    if include_employment_override and (employer or title):
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


def tag_body_chunks(
    chunks: list[Document], *, knowledge_file: str | None = None
) -> list[Document]:
    out: list[Document] = []
    for d in chunks:
        meta = dict(d.metadata)
        meta["source"] = "resume_body"
        meta["authoritative"] = False
        meta["priority"] = 100
        if knowledge_file:
            meta["knowledge_file"] = knowledge_file
        out.append(Document(page_content=d.page_content, metadata=meta))
    return out
