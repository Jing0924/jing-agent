"""Google Calendar: natural language → events.insert (single-user OAuth on server)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from memoir_rag.config import google_calendar_oauth_configured, load_env
from memoir_rag.schemas.calendar import (
    CalendarEventCreatedResponse,
    CalendarFromTextBody,
    CalendarStatusResponse,
)
from memoir_rag.services.calendar_google import (
    CalendarOAuthNotConfiguredError,
    insert_primary_event,
)
from memoir_rag.services.calendar_nlp import format_rfc3339_z, parse_event_from_text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["calendar"])


@router.get("/api/calendar/status", response_model=CalendarStatusResponse)
def calendar_status():
    load_env()
    return CalendarStatusResponse(configured=google_calendar_oauth_configured())


@router.post("/api/calendar/events/from-text", response_model=CalendarEventCreatedResponse)
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

    try:
        ev = parse_event_from_text(body.text)
    except EnvironmentError as e:
        logger.warning("Calendar NLP missing Gemini key: %s", e)
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"無法解析事件：{e}",
        ) from e
    except Exception as e:
        logger.exception("Calendar NLP failed: %s", e)
        raise HTTPException(
            status_code=400,
            detail="無法將文字解析為行事曆事件，請換個說法再試。",
        ) from e

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
        id=eid,
        html_link=link,
        summary=summ,
        start=format_rfc3339_z(ev.start),
        end=format_rfc3339_z(ev.end),
    )
