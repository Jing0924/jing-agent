"""Extract birthday facts from Markdown tables; compute western-style (實歲) age."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

DATE_RE = re.compile(r"\b(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})\b")


def _strip_cell(s: str) -> str:
    return (
        s.replace("**", "")
        .strip()
        .strip("*")
        .strip()
    )


def _parse_date_cell(raw: str) -> date | None:
    """Parse YYYY/MM/DD or YYYY-MM-DD; skip placeholders."""
    cell = raw.strip()
    if not cell or "待補" in cell:
        return None
    m = DATE_RE.search(cell)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _split_pipe_row(line: str) -> list[str]:
    line = line.rstrip("\n")
    if not line.strip().startswith("|"):
        return []
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    parts = [_strip_cell(x) if x.strip() else x.strip() for x in inner.split("|")]
    while parts and not parts[-1]:
        parts.pop()
    return parts


def _row_is_separator_cells(row: list[str]) -> bool:
    """GFM table second row: | --- | --- |."""
    if len(row) < 2:
        return False
    for c in row:
        t = c.strip()
        if not t:
            continue
        if not re.fullmatch(r":?-{3,}:?", t):
            return False
    return True


def _first_hash_heading(text: str) -> str | None:
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _iter_markdown_tables(text: str) -> list[list[list[str]]]:
    """Return list of tables; each table is list of rows; each row is list of cell strings."""
    lines = text.splitlines()
    tables: list[list[list[str]]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "|" not in line or line.strip().startswith("```"):
            i += 1
            continue
        block: list[list[str]] = []
        while i < len(lines) and "|" in lines[i] and not lines[i].strip().startswith("```"):
            row = _split_pipe_row(lines[i])
            if row:
                block.append(row)
            i += 1
        if len(block) >= 2:
            tables.append(block)
    return tables


def compute_real_age(birthdate: date, today: date) -> int:
    """Western-style complete years (實歲)."""
    age = today.year - birthdate.year
    if (today.month, today.day) < (birthdate.month, birthdate.day):
        age -= 1
    return age


@dataclass(frozen=True)
class BirthdayRecord:
    name: str
    role: str | None
    birthdate: date
    source_file: str


def extract_birthdays(text: str, *, source: str) -> list[BirthdayRecord]:
    """Parse markdown tables for 生日 / 出生日期; skip unparseable rows."""
    default_name = _first_hash_heading(text)
    out: list[BirthdayRecord] = []
    seen: set[tuple[str, date]] = set()

    def add(name: str, role: str | None, bd: date) -> None:
        name = name.strip()
        if not name:
            return
        key = (name, bd)
        if key in seen:
            return
        seen.add(key)
        out.append(
            BirthdayRecord(
                name=name,
                role=role if role else None,
                birthdate=bd,
                source_file=source,
            )
        )

    for table in _iter_markdown_tables(text):
        if not table:
            continue
        if len(table) > 1 and _row_is_separator_cells(table[1]):
            header_row = table[0]
            rest = table[2:]
        else:
            header_row = table[0]
            rest = table[1:]

        norm_headers = [_strip_cell(c) for c in header_row]
        try:
            bi = next(
                i
                for i, h in enumerate(norm_headers)
                if h in ("生日", "出生日期")
            )
        except StopIteration:
            bi = -1
        name_i = next((i for i, h in enumerate(norm_headers) if h == "姓名"), -1)
        role_i = next((i for i, h in enumerate(norm_headers) if h in ("稱謂", "角色")), -1)

        if bi >= 0 and rest:
            for row in rest:
                if len(row) <= bi:
                    continue
                bd = _parse_date_cell(row[bi])
                if bd is None:
                    continue
                name = (
                    row[name_i].strip()
                    if 0 <= name_i < len(row) and row[name_i].strip()
                    else (default_name or "")
                )
                role = None
                if 0 <= role_i < len(row) and row[role_i].strip():
                    role = _strip_cell(row[role_i])
                if not name and default_name:
                    name = default_name
                if name:
                    add(name, role, bd)
            continue

        # Key–value style: label in first column, value in second (e.g. profile table)
        for row in table:
            if len(row) < 2:
                continue
            label = _strip_cell(row[0])
            value_cell = row[1] if len(row) > 1 else ""
            if label not in ("生日", "出生日期"):
                continue
            bd = _parse_date_cell(value_cell)
            if bd is None:
                continue
            name = default_name or ""
            for r2 in table:
                if len(r2) < 2:
                    continue
                l2 = _strip_cell(r2[0])
                if l2 == "姓名" and r2[1].strip():
                    name = _strip_cell(r2[1])
                    break
            role = None
            for r2 in table:
                if len(r2) < 2:
                    continue
                l2 = _strip_cell(r2[0])
                if l2 in ("稱謂", "角色") and r2[1].strip():
                    role = _strip_cell(r2[1])
                    break
            if name:
                add(name, role, bd)

    return out
