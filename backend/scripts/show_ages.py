"""Print computed ages from knowledge Markdown (Asia/Taipei today).

Run from the backend directory::

    python scripts/show_ages.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from memoir_rag.config import PROJECT_ROOT, resolve_knowledge_md_paths
from memoir_rag.loaders.birthdays import compute_real_age, extract_birthdays


def main() -> None:
    paths = resolve_knowledge_md_paths()
    rows: list = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        try:
            src = str(p.resolve().relative_to(PROJECT_ROOT.resolve()))
        except ValueError:
            src = p.as_posix()
        rows.extend(extract_birthdays(text, source=src))
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    print(f"今日 {today.strftime('%Y/%m/%d')} (Asia/Taipei)")
    for r in sorted(rows, key=lambda x: (x.birthdate, x.name)):
        age = compute_real_age(r.birthdate, today)
        role = f" {r.role}" if r.role else ""
        print(f"{r.name}{role} {r.birthdate.strftime('%Y/%m/%d')}  → {age}")


if __name__ == "__main__":
    main()
