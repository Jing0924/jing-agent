"""Google Calendar API client built from OAuth refresh token (single user)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from memoir_rag.config import calendar_default_timezone, google_calendar_oauth_configured

CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"


class CalendarOAuthNotConfiguredError(RuntimeError):
    pass


def _credentials() -> Credentials:
    if not google_calendar_oauth_configured():
        raise CalendarOAuthNotConfiguredError(
            "行事曆未連結 Google：請在 Google Cloud 啟用 Calendar API，"
            "建立 OAuth 桌面應用程式憑證，執行 `python scripts/oauth_google_calendar.py` "
            "取得 refresh token，並設定 GOOGLE_CALENDAR_CLIENT_ID、"
            "GOOGLE_CALENDAR_CLIENT_SECRET、GOOGLE_CALENDAR_REFRESH_TOKEN。"
        )

    import os

    return Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_CALENDAR_REFRESH_TOKEN"].strip(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CALENDAR_CLIENT_ID"].strip(),
        client_secret=os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"].strip(),
        scopes=[CALENDAR_EVENTS_SCOPE],
    )


def calendar_service():  # googleapiclient discovery Resource
    creds = _credentials()
    creds.refresh(Request())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _google_datetime_payload(dt: datetime, tz_name: str) -> dict[str, str]:
    zi = ZoneInfo(tz_name)
    local = dt.astimezone(zi)
    return {
        "dateTime": local.replace(microsecond=0).isoformat(),
        "timeZone": tz_name,
    }


def insert_primary_event(
    *,
    summary: str,
    start: datetime,
    end: datetime,
    location: str | None,
    description: str | None,
    tz_name: str | None = None,
) -> dict[str, Any]:
    tz = tz_name or calendar_default_timezone()
    svc = calendar_service()

    body: dict[str, Any] = {
        "summary": summary,
        "start": _google_datetime_payload(start, tz),
        "end": _google_datetime_payload(end, tz),
    }
    if location and location.strip():
        body["location"] = location.strip()
    if description and description.strip():
        body["description"] = description.strip()

    try:
        return svc.events().insert(calendarId="primary", body=body).execute()
    except HttpError as e:
        raise RuntimeError(f"Google Calendar API error ({e.status_code}): {e}") from e
