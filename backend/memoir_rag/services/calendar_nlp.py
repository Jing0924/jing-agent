"""Parse natural-language event text with Gemini (independent from RAG chain)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from memoir_rag.config import (
    LLM_MODEL,
    calendar_default_duration_minutes,
    calendar_default_timezone,
    load_env,
    require_google_api_key,
)


class LlmParsedEvent(BaseModel):
    """Structured extraction; times are ISO 8601, may omit offset (local wall time)."""

    title: Annotated[
        str,
        Field(description="Brief event title. No fabricated addresses."),
    ]
    start: Annotated[
        str,
        Field(description="ISO 8601 datetime (prefer offset e.g. +08:00, or naive local)."),
    ]
    end: Annotated[
        str | None,
        Field(description="ISO 8601 end datetime; omit if unknown — server adds default duration."),
    ] = None
    location: str | None = Field(
        default=None,
        description="Physical or virtual location only if the user explicitly mentioned it.",
    )
    description: str | None = None


def _system_prompt(now_local: datetime, tz_name: str, default_duration_minutes: int) -> str:
    weekdays = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    wd = weekdays[now_local.weekday()]
    iso_date = now_local.date().isoformat()
    iso_full = now_local.replace(microsecond=0).isoformat()
    return f"""你是行事曆事件解析助手。使用者以自然語言描述一筆將建立到 Google 行事曆的事件。

伺服器視角的現在（以此為「今天」與「明天」等錨點）：
- 時區（IANA）：{tz_name}
- 現在（該時區）：{iso_full} ({wd})
- 「今天」的日期（該時區）：{iso_date}

規則：
- 將相對時間（明天、下週一、今天下午三點等）換算成 ISO 8601 的開始時間；若為當日牆上時間無偏移，可不帶時區偏移（伺服器會套用 {tz_name}）。
- 若使用者完全沒有提到結束時間，將 end 留白（null），伺服器將以開始時間加 {default_duration_minutes} 分鐘作為結束。
- 不要臆造門牌或具體地址；地点僅在用戶口述時填入 location。
- title 簡潔（可概括活動類型）；若無單獨標題可循，可用使用者句子的簡短版本。
輸出僅為結構化欄位（由系統強制）；不要冗長說明。"""


def _normalize_iso_datetime(s: str, default_tz_name: str) -> datetime:
    raw = (s or "").strip()
    if not raw:
        raise ValueError("Empty datetime.")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(default_tz_name))
    return dt


@dataclass(frozen=True)
class NormalizedEvent:
    title: str
    start: datetime
    end: datetime
    location: str | None
    description: str | None


def parse_event_from_text(text: str) -> NormalizedEvent:
    """Use Gemini structured output to parse user's natural language."""

    load_env()
    require_google_api_key()

    tz_name = calendar_default_timezone()
    duration_min = calendar_default_duration_minutes()

    now_local = datetime.now(ZoneInfo(tz_name))
    sys = _system_prompt(now_local, tz_name, duration_min)

    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)
    structured = llm.with_structured_output(LlmParsedEvent)
    out = structured.invoke(
        [
            SystemMessage(content=sys),
            HumanMessage(content=text.strip()),
        ]
    )

    if not isinstance(out, LlmParsedEvent):
        raise ValueError("LLM returned an unexpected structured payload.")

    start = _normalize_iso_datetime(out.start, tz_name)

    if out.end:
        end = _normalize_iso_datetime(out.end, tz_name)
        if end <= start:
            end = start + timedelta(minutes=duration_min)
    else:
        end = start + timedelta(minutes=duration_min)

    title = out.title.strip() or text.strip()
    loc = out.location.strip() if out.location and out.location.strip() else None
    desc = out.description.strip() if out.description and out.description.strip() else None

    return NormalizedEvent(
        title=title,
        start=start,
        end=end,
        location=loc,
        description=desc,
    )


def format_rfc3339_z(dt: datetime) -> str:
    """RFC3339 in UTC with Z suffix for JSON responses."""

    u = dt.astimezone(UTC).replace(tzinfo=UTC).replace(microsecond=0)
    return u.strftime("%Y-%m-%dT%H:%M:%SZ")
