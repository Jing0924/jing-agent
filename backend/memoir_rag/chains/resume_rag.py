"""Resume RAG: Chroma persistence, authoritative docs at ingest, metadata-sorted retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Sequence
from zoneinfo import ZoneInfo

from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from memoir_rag.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_MODEL,
    LLM_MODEL,
    PROJECT_ROOT,
    knowledge_fingerprint_bytes,
    llm_temperature,
    override_fields,
    require_google_api_key,
    resolve_knowledge_md_paths,
)
from memoir_rag.loaders.birthdays import extract_birthdays
from memoir_rag.loaders.canonical import (
    build_age_facts_document,
    build_authoritative_documents,
    tag_body_chunks,
)
from memoir_rag.loaders.resume import load_resume
from memoir_rag.loaders.vectorstore import build_or_load_chroma, compute_fingerprint
from memoir_rag.prompts.resume import SYSTEM, prompt_digest
from memoir_rag.splitters.resume import split_resume


def _answer_text(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if hasattr(val, "content"):
        inner = getattr(val, "content")
        if isinstance(inner, str):
            return inner
        if isinstance(inner, list):
            parts: list[str] = []
            for block in inner:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif hasattr(block, "text"):
                    parts.append(str(getattr(block, "text")))
                elif isinstance(block, str):
                    parts.append(block)
            return "".join(parts)
    return str(val)


def iter_answer_stream_deltas(chain: Any, input_payload: dict[str, Any]) -> Iterator[str]:
    """Yield incremental answer text from chain.stream (cumulative `answer` or message chunks)."""
    prev = ""
    for chunk in chain.stream(input_payload):
        if not isinstance(chunk, dict):
            continue
        text = _answer_text(chunk.get("answer"))
        if not text:
            continue
        if text.startswith(prev) and len(text) >= len(prev):
            if len(text) > len(prev):
                yield text[len(prev) :]
                prev = text
        else:
            yield text
            prev = text


@dataclass(frozen=True)
class ResumeRagChainBundle:
    chain: Any
    embedding_fingerprint: str
    prompt_sha256: str
    llm_model: str


def _sort_by_metadata(docs: list[Document]) -> list[Document]:
    return sorted(
        docs,
        key=lambda d: (
            not d.metadata.get("authoritative", False),
            d.metadata.get("priority", 100),
        ),
    )


def _merge_authoritative_and_retrieved(
    authoritative_prefix: list[Document], retrieved: list[Document]
) -> list[Document]:
    merged: list[Document] = []
    seen: set[str] = set()
    for d in authoritative_prefix:
        merged.append(d)
        seen.add(d.page_content)
    for d in retrieved:
        if d.page_content not in seen:
            merged.append(d)
            seen.add(d.page_content)
    return _sort_by_metadata(merged)


def build_resume_rag_chain(knowledge_paths: Sequence[Path] | None = None) -> ResumeRagChainBundle:
    """多份 Markdown（`knowledge/` 下（含子目錄）所有 `.md` 優先；否則 `resume.md`，皆相對於應用程式根 backend/）→ 向量庫與檢索問答鏈。"""
    paths = (
        [Path(p).resolve() for p in knowledge_paths]
        if knowledge_paths is not None
        else resolve_knowledge_md_paths()
    )
    if not paths:
        raise ValueError("knowledge_paths 不可為空。")

    multi_file = len(paths) > 1

    require_google_api_key()

    raw_for_fp = knowledge_fingerprint_bytes(paths)
    employer, title = override_fields()
    pd = prompt_digest()
    fingerprint = compute_fingerprint(
        raw_for_fp,
        CHUNK_SIZE,
        CHUNK_OVERLAP,
        EMBEDDING_MODEL,
        employer,
        title,
    )

    birthdays_all: list = []
    for resume_path in paths:
        raw = resume_path.read_text(encoding="utf-8")
        try:
            source = str(resume_path.resolve().relative_to(PROJECT_ROOT.resolve()))
        except ValueError:
            source = resume_path.as_posix()
        birthdays_all.extend(extract_birthdays(raw, source=source))

    all_docs: list[Document] = []
    for i, resume_path in enumerate(paths):
        data = load_resume(resume_path)
        full_text = data[0].page_content if data else ""
        stem = resume_path.stem if multi_file else None
        authoritative = build_authoritative_documents(
            full_text,
            employer,
            title,
            include_employment_override=(i == 0),
            header_stem=stem,
        )
        kfile = f"{resume_path.stem}.md" if multi_file else None
        body_chunks = tag_body_chunks(split_resume(data), knowledge_file=kfile)
        all_docs.extend(authoritative)
        all_docs.extend(body_chunks)

    authoritative_prefix = [
        d
        for d in all_docs
        if d.metadata.get("authoritative")
        and d.metadata.get("priority", 999) <= 10
    ]

    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = build_or_load_chroma(all_docs, embeddings, fingerprint, pd)

    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=llm_temperature(), streaming=True)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM),
            ("human", "{input}"),
        ]
    )
    combine_chain = create_stuff_documents_chain(llm, prompt)

    base_retriever = vectorstore.as_retriever(search_kwargs={"k": 10})

    def _retriever(payload: dict) -> list[Document]:
        today = datetime.now(ZoneInfo("Asia/Taipei")).date()
        age_doc = build_age_facts_document(birthdays_all, today)
        prefix = ([age_doc] if age_doc else []) + authoritative_prefix
        retrieved = base_retriever.invoke(payload["input"])
        return _merge_authoritative_and_retrieved(prefix, retrieved)

    retriever = RunnableLambda(_retriever)

    chain = create_retrieval_chain(retriever, combine_chain)
    return ResumeRagChainBundle(
        chain=chain,
        embedding_fingerprint=fingerprint,
        prompt_sha256=pd,
        llm_model=LLM_MODEL,
    )
