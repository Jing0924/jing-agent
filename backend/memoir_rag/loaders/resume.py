"""Load and normalize resume Markdown into Documents."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document


def _clean_resume_text(text: str) -> str:
    """移除 NUL 與碎片化空白，並 NFKC 正規化康熙部首相容字與常見缺字。"""
    text = text.replace("\x00", "")
    text = text.replace("\r", "\n")
    text = re.sub(r"[\s\u3000]+", " ", text)
    text = text.strip()
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("助理工師", "助理工程師")
    return text


def _clean_documents(docs: list[Document]) -> list[Document]:
    return [
        Document(page_content=_clean_resume_text(d.page_content), metadata=d.metadata)
        for d in docs
    ]


def load_resume(path: str | Path) -> list[Document]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"找不到履歷檔：{path.resolve()}")
    loader = TextLoader(str(path), encoding="utf-8")
    return _clean_documents(loader.load())
