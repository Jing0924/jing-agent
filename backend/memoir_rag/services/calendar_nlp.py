"""Parse natural-language event text with Gemini (independent from RAG chain)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field, model_validator

from memoir_rag.config import (
    LLM_MODEL,
    calendar_default_duration_minutes,
    calendar_default_timezone,
    load_env,
    require_google_api_key,
)


class LlmCalendarIntent(BaseModel):
    """Single schema for Gemini: unions are unsupported; branch on intent in model_validator."""

    intent: Annotated[
        Literal["create", "delete"],
        Field(description='Must be "create" for new events or "delete" to remove an existing event.'),
    ]
    title: Annotated[
        str | None,
        Field(default=None, description="(create) Brief event title. No fabricated addresses."),
    ] = None
    start: Annotated[
        str | None,
        Field(default=None, description="(create) ISO 8601 datetime (prefer offset +08:00, or naive local)."),
    ] = None
    end: Annotated[
        str | None,
        Field(
            default=None,
            description="(create) ISO 8601 end; omit if unknown — server adds default duration.",
        ),
    ] = None
    location: str | None = Field(
        default=None,
        description="(create) Physical or virtual location only if the user explicitly mentioned it.",
    )
    description: str | None = Field(default=None, description="(create) Extra notes only if user said.")
    summary_substring: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "(delete) Optional keyword or phrase to match event summary (case-insensitive substring), "
                "e.g. 朵頤 or 開會. "
                "If the user only gives a time and does not name the event, set null or omit; "
                "the server deletes by time window overlap only (still requires exactly one match)."
            ),
        ),
    ] = None
    window_start: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "(delete) ISO 8601 search window start "
                "(phrases like 明天下午; same timezone rules as create)."
            ),
        ),
    ] = None
    window_end: Annotated[
        str | None,
        Field(
            default=None,
            description="(delete) ISO 8601 end of search window.",
        ),
    ] = None

    @model_validator(mode="after")
    def fields_match_intent(self) -> Self:
        if self.intent == "create":
            if not (self.title and self.title.strip()):
                raise ValueError("建立行程須提供標題。")
            if not (self.start and self.start.strip()):
                raise ValueError("建立行程須提供開始時間。")
            return self
        if self.intent == "delete":
            if not (self.window_start and self.window_start.strip()):
                raise ValueError("刪除意圖須包含搜尋時間範圍（開始）。")
            if not (self.window_end and self.window_end.strip()):
                raise ValueError("刪除意圖須包含搜尋時間範圍（結束）。")
            return self
        raise ValueError(f"unsupported intent {self.intent!r}")  # pragma: no cover


def _system_prompt(now_local: datetime, tz_name: str, default_duration_minutes: int) -> str:
    weekdays = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    wd = weekdays[now_local.weekday()]
    iso_date = now_local.date().isoformat()
    iso_full = now_local.replace(microsecond=0).isoformat()
    return f"""你是行事曆助理。使用者以自然語言描述「建立」或「刪除」Google 行事曆（primary）中的一筆事件。

伺服器視角的現在（以此為「今天」與「明天」等錨點）：
- 時區（IANA）：{tz_name}
- 現在（該時區）：{iso_full} ({wd})
- 「今天」的日期（該時區）：{iso_date}

意圖判斷（必須嚴格）：
- **create**：使用者要安排、新增、記一筆行程；沒有表達取消或刪除既有行程。
- **delete**：使用者明確要**取消、刪除、拿掉、不要、撤銷**等**既有**行程；此時 intent 必須為 delete。
- 若僅在描述未來要做的事（即使語氣消極），沒有針對「已有那一筆」的刪除意圖 → create。

**create** 時輸出欄位：
- 將相對時間換算成 ISO 8601；若為當日牆上時間無偏移，可不帶時區偏移（伺服器會套用 {tz_name}）。
- 若未提到結束時間，end 留白（null），伺服器以開始時間加 {default_duration_minutes} 分鐘作為結束。
- 不要臆造地址；地点僅在用戶口述時填入 location。
- title 簡潔。

**delete** 時輸出欄位：
- window_start / window_end：**必填**。該行程預期發生的**搜尋時間範圍**（ISO 8601），依「明天下午一點」「下週一早上」等與上述錨點換算；範圍應盡量對應使用者說的時段（可略寬以涵蓋該事件，但勿涵蓋無關的整週除非使用者只說下週）。
- summary_substring：若有事件名稱或關鍵字，填入可與標題做不分大小寫子字串比對的片段。**若使用者只給時間、未提事件名稱，可留空（null）**；伺服器僅依時間窗與行程重疊篩選（仍須在窗內恰好一筆才可刪）。

輸出僅為結構化欄位；不要冗長說明。"""


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


@dataclass(frozen=True)
class DeleteQuery:
    summary_substring: str | None
    window_start: datetime
    window_end: datetime


def parse_calendar_text(text: str) -> NormalizedEvent | DeleteQuery:
    """Parse natural language into a create payload or a delete search query."""

    load_env()
    require_google_api_key()

    tz_name = calendar_default_timezone()
    duration_min = calendar_default_duration_minutes()

    now_local = datetime.now(ZoneInfo(tz_name))
    sys = _system_prompt(now_local, tz_name, duration_min)

    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)
    structured = llm.with_structured_output(LlmCalendarIntent)
    out = structured.invoke(
        [
            SystemMessage(content=sys),
            HumanMessage(content=text.strip()),
        ]
    )

    if out.intent == "create":
        start = _normalize_iso_datetime(out.start, tz_name)

        if out.end:
            end = _normalize_iso_datetime(out.end, tz_name)
            if end <= start:
                end = start + timedelta(minutes=duration_min)
        else:
            end = start + timedelta(minutes=duration_min)

        title = (out.title or "").strip() or text.strip()
        loc = out.location.strip() if out.location and out.location.strip() else None
        desc = out.description.strip() if out.description and out.description.strip() else None

        return NormalizedEvent(
            title=title,
            start=start,
            end=end,
            location=loc,
            description=desc,
        )

    raw_sub = out.summary_substring
    sub: str | None = (raw_sub.strip() if raw_sub and raw_sub.strip() else None)
    ws = _normalize_iso_datetime(out.window_start, tz_name)
    we = _normalize_iso_datetime(out.window_end, tz_name)
    if we < ws:
        ws, we = we, ws
    if ws == we:
        we = ws + timedelta(hours=24)
    return DeleteQuery(summary_substring=sub, window_start=ws, window_end=we)


def parse_event_from_text(text: str) -> NormalizedEvent:
    """Use Gemini structured output for create-only parsing (backward compatible)."""

    parsed = parse_calendar_text(text)
    if isinstance(parsed, DeleteQuery):
        raise ValueError("此為刪除意圖，不是建立行程；請換個說法。")
    return parsed


def format_rfc3339_z(dt: datetime) -> str:
    """RFC3339 in UTC with Z suffix for JSON responses."""

    u = dt.astimezone(UTC).replace(tzinfo=UTC).replace(microsecond=0)
    return u.strftime("%Y-%m-%dT%H:%M:%SZ")
