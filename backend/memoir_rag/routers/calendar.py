"""Google Calendar: natural language → events.insert / list+delete (single-user OAuth on server)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Union

from fastapi import APIRouter, HTTPException, Query
from zoneinfo import ZoneInfo

from memoir_rag.config import calendar_default_timezone, google_calendar_oauth_configured, load_env
from memoir_rag.schemas.calendar import (
    CalendarEventCreatedResponse,
    CalendarEventDeletedResponse,
    CalendarEventListItem,
    CalendarEventsListResponse,
    CalendarFromTextBody,
    CalendarStatusResponse,
)
from memoir_rag.services.calendar_google import (
    CalendarOAuthNotConfiguredError,
    delete_primary_event,
    event_bounds_utc,
    event_overlaps_window,
    insert_primary_event,
    list_primary_events,
)
from memoir_rag.services.calendar_nlp import DeleteQuery, format_rfc3339_z, parse_calendar_text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["calendar"])


def _format_conflict_detail(ev: dict, tz_name: str) -> str:
    summ = (ev.get("summary") or "(無標題)").strip()
    st, _ = event_bounds_utc(ev, tz_name)
    t = format_rfc3339_z(st)
    return f"- {summ}（{t}）"


def _naive_local(dt: datetime, tz_name: str) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(tz_name))
    return dt.astimezone(ZoneInfo(tz_name))


@router.get("/api/calendar/status", response_model=CalendarStatusResponse)
def calendar_status():
    load_env()
    return CalendarStatusResponse(
        configured=google_calendar_oauth_configured(),
        default_timezone=calendar_default_timezone(),
    )


def _summarize_list_event(ev: dict, tz_name: str) -> CalendarEventListItem:
    st, et = event_bounds_utc(ev, tz_name)
    return CalendarEventListItem(
        id=ev.get("id") or "",
        summary=(ev.get("summary") or "").strip() or "(無標題)",
        start=format_rfc3339_z(st),
        end=format_rfc3339_z(et),
        location=(ev.get("location") or "").strip(),
        html_link=(ev.get("htmlLink") or "").strip(),
    )


@router.get("/api/calendar/events", response_model=CalendarEventsListResponse)
def calendar_list_events(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
):
    """List primary calendar events in [from, to). Defaults: today 00:00 through +7 days in configured timezone."""

    load_env()
    if not google_calendar_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google 行事曆尚未設定：請完成 OAuth 並在 .env 設定 "
                "GOOGLE_CALENDAR_CLIENT_ID、GOOGLE_CALENDAR_CLIENT_SECRET、"
                "GOOGLE_CALENDAR_REFRESH_TOKEN（勿提交至 git）。"
            ),
        )
    tz_name = calendar_default_timezone()
    zi = ZoneInfo(tz_name)
    now = datetime.now(zi)

    if from_ is None and to is None:
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = time_min + timedelta(days=7)
    elif from_ is None:
        time_max = _naive_local(to, tz_name)
        time_min = time_max - timedelta(days=7)
    elif to is None:
        time_min = _naive_local(from_, tz_name)
        time_max = time_min + timedelta(days=7)
    else:
        time_min = _naive_local(from_, tz_name)
        time_max = _naive_local(to, tz_name)

    if time_max <= time_min:
        raise HTTPException(
            status_code=400,
            detail="參數 to 必須晚於 from。",
        )

    time_min_utc = time_min.astimezone(UTC)
    time_max_utc = time_max.astimezone(UTC)

    try:
        raw = list_primary_events(time_min_utc, time_max_utc, tz_name=tz_name)
    except CalendarOAuthNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except RuntimeError as e:
        logger.exception("Google Calendar list failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e

    visible = [ev for ev in raw if ev.get("status") != "cancelled"]
    items = [_summarize_list_event(ev, tz_name) for ev in visible]
    return CalendarEventsListResponse(timezone=tz_name, events=items)


@router.post(
    "/api/calendar/events/from-text",
    response_model=Union[CalendarEventCreatedResponse, CalendarEventDeletedResponse],
)
def calendar_event_from_text(body: CalendarFromTextBody):
    load_env()
    if not google_calendar_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google 行事曆尚未設定：請完成 OAuth 並在 .env 設定 "
                "GOOGLE_CALENDAR_CLIENT_ID、GOOGLE_CALENDAR_CLIENT_SECRET、"
                "GOOGLE_CALENDAR_REFRESH_TOKEN（勿提交至 git）。"
            ),
        )

    tz_name = calendar_default_timezone()

    try:
        parsed = parse_calendar_text(body.text)
    except EnvironmentError as e:
        logger.warning("Calendar NLP missing Gemini key: %s", e)
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"無法解析：{e}",
        ) from e
    except Exception as e:
        logger.exception("Calendar NLP failed: %s", e)
        raise HTTPException(
            status_code=400,
            detail="無法將文字解析為行事曆操作，請換個說法再試。",
        ) from e

    if isinstance(parsed, DeleteQuery):
        return _calendar_delete(parsed, tz_name)

    ev = parsed
    try:
        created = insert_primary_event(
            summary=ev.title,
            start=ev.start,
            end=ev.end,
            location=ev.location,
            description=ev.description,
        )
    except CalendarOAuthNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except RuntimeError as e:
        logger.exception("Google Calendar insert failed: %s", e)
        raise HTTPException(
            status_code=502,
            detail=str(e),
        ) from e

    link = created.get("htmlLink") or ""
    summ = created.get("summary") or ev.title
    eid = created.get("id") or ""
    return CalendarEventCreatedResponse(
        result="created",
        id=eid,
        html_link=link,
        summary=summ,
        start=format_rfc3339_z(ev.start),
        end=format_rfc3339_z(ev.end),
    )


def _calendar_delete(q: DeleteQuery, tz_name: str) -> CalendarEventDeletedResponse:
    needle = q.summary_substring.lower() if q.summary_substring else None
    try:
        rows = list_primary_events(q.window_start, q.window_end, tz_name=tz_name)
    except CalendarOAuthNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except RuntimeError as e:
        logger.exception("Google Calendar list failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e

    candidates = [
        ev
        for ev in rows
        if ev.get("status") != "cancelled"
        and (needle is None or needle in (ev.get("summary") or "").lower())
        and event_overlaps_window(ev, q.window_start, q.window_end, tz_name)
    ]

    if not candidates:
        if needle is None:
            detail = "此時間範圍內沒有可刪除的行程。"
        else:
            detail = "在此時間範圍內找不到符合摘要的行程；請改寫關鍵字或時間再試。"
        raise HTTPException(
            status_code=400,
            detail=detail,
        )
    if len(candidates) > 1:
        lines = [_format_conflict_detail(ev, tz_name) for ev in candidates[:12]]
        extra = ""
        if len(candidates) > 12:
            extra = f"\n… 另有 {len(candidates) - 12} 筆"
        raise HTTPException(
            status_code=409,
            detail="找到多筆符合的行程，請說得更具體後再試：\n" + "\n".join(lines) + extra,
        )

    ev = candidates[0]
    eid = ev.get("id") or ""
    st, et = event_bounds_utc(ev, tz_name)
    summ = (ev.get("summary") or "").strip()
    try:
        delete_primary_event(eid)
    except CalendarOAuthNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except RuntimeError as e:
        logger.exception("Google Calendar delete failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e

    return CalendarEventDeletedResponse(
        result="deleted",
        id=eid,
        summary=summ or "(無標題)",
        start=format_rfc3339_z(st),
        end=format_rfc3339_z(et),
    )
