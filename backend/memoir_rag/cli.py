"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from learn_langchain.config import PROJECT_ROOT, load_env
from learn_langchain.chains.resume_rag import build_resume_rag_chain


def main() -> None:
    load_env()

    parser = argparse.ArgumentParser(
        description="以 resume.md 為知識庫，根據履歷 RAG 回答問題。"
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="要向履歷問答鏈提出的問題（可為多個詞，會以空格連接）",
    )
    args = parser.parse_args()
    query = " ".join(args.question).strip()
    if not query:
        parser.print_usage()
        print(
            "learn-langchain.py: error: 請提供問題，例如："
            'python learn-langchain.py "根據這份履歷，你最擅長的技術是什麼？"',
            file=sys.stderr,
        )
        sys.exit(1)

    resume_md = PROJECT_ROOT / "resume.md"
    chain = build_resume_rag_chain(resume_md)

    print(f"--- 問題 ---\n{query}\n")
    result = chain.invoke({"input": query})
    print(f"--- 回答 ---\n{result['answer']}")


if __name__ == "__main__":
    main()
