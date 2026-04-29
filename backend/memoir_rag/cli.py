"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

from memoir_rag.config import load_env
from memoir_rag.chains.resume_rag import build_resume_rag_chain, iter_answer_stream_deltas


def main() -> None:
    load_env()

    parser = argparse.ArgumentParser(
        description=(
            "以 knowledge/*.md（若無則 resume.md）為知識庫，根據履歷 RAG 回答問題。"
        )
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="要向履歷問答鏈提出的問題（可為多個詞，會以空格連接）",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="以串流方式輸出回答（預設為一次顯示完整結果）",
    )
    args = parser.parse_args()
    query = " ".join(args.question).strip()
    if not query:
        parser.print_usage()
        print(
            "memoir_ask.py: error: 請提供問題，例如於 backend/："
            'python memoir_ask.py "根據這份履歷，你最擅長的技術是什麼？"',
            file=sys.stderr,
        )
        sys.exit(1)

    bundle = build_resume_rag_chain()
    chain = bundle.chain

    print(f"--- 問題 ---\n{query}\n")
    if args.stream:
        print("--- 回答 ---")
        for delta in iter_answer_stream_deltas(chain, {"input": query}):
            print(delta, end="", flush=True)
        print()
    else:
        result = chain.invoke({"input": query})
        print(f"--- 回答 ---\n{result['answer']}")


if __name__ == "__main__":
    main()
