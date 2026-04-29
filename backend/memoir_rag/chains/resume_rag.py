"""Resume RAG: Chroma persistence, authoritative docs at ingest, metadata-sorted retrieval."""

from __future__ import annotations

from pathlib import Path

from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from learn_langchain.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_MODEL,
    LLM_MODEL,
    require_google_api_key,
    override_fields,
)
from learn_langchain.loaders.canonical import build_authoritative_documents, tag_body_chunks
from learn_langchain.loaders.resume import load_resume
from learn_langchain.loaders.vectorstore import build_or_load_chroma, compute_fingerprint
from learn_langchain.prompts.resume import SYSTEM
from learn_langchain.splitters.resume import split_resume


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


def build_resume_rag_chain(resume_path: str | Path):
    """履歷 Markdown → 持久化向量庫與檢索問答鏈。"""
    resume_path = Path(resume_path)
    require_google_api_key()

    resume_bytes = resume_path.read_bytes()
    employer, title = override_fields()
    fingerprint = compute_fingerprint(
        resume_bytes,
        CHUNK_SIZE,
        CHUNK_OVERLAP,
        EMBEDDING_MODEL,
        employer,
        title,
    )

    data = load_resume(resume_path)
    full_text = data[0].page_content if data else ""

    authoritative = build_authoritative_documents(full_text, employer, title)
    body_chunks = tag_body_chunks(split_resume(data))
    all_docs: list[Document] = list(authoritative) + body_chunks

    authoritative_prefix = [
        d
        for d in all_docs
        if d.metadata.get("authoritative")
        and d.metadata.get("priority", 999) <= 10
    ]

    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = build_or_load_chroma(all_docs, embeddings, fingerprint)

    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM),
            ("human", "{input}"),
        ]
    )
    combine_chain = create_stuff_documents_chain(llm, prompt)

    base_retriever = vectorstore.as_retriever(search_kwargs={"k": 10})

    def _retriever(payload: dict) -> list[Document]:
        retrieved = base_retriever.invoke(payload["input"])
        return _merge_authoritative_and_retrieved(authoritative_prefix, retrieved)

    retriever = RunnableLambda(_retriever)

    return create_retrieval_chain(retriever, combine_chain)
