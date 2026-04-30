"""Google Calendar API client built from OAuth refresh token (single user)."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from memoir_rag.config import calendar_default_timezone, google_calendar_oauth_configured

CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"


def _format_rfc3339_z(dt: datetime) -> str:
    u = dt.astimezone(UTC).replace(tzinfo=UTC).replace(microsecond=0)
    return u.strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _parse_iso_maybe_z(s: str) -> datetime:
    raw = s.replace("Z", "+00:00")
    return datetime.fromisoformat(raw)


def event_bounds_utc(ev: dict[str, Any], tz_name: str) -> tuple[datetime, datetime]:
    """Inclusive-ish start / end instants for overlap checks (timed + all-day)."""

    zi = ZoneInfo(tz_name)

    start_block = ev.get("start") or {}
    end_block = ev.get("end") or {}

    if start_block.get("dateTime"):
        st = _parse_iso_maybe_z(start_block["dateTime"])
        if st.tzinfo is None:
            tz = start_block.get("timeZone") or tz_name
            st = st.replace(tzinfo=ZoneInfo(tz))
        st_utc = st.astimezone(UTC)
    elif start_block.get("date"):
        d0 = datetime.fromisoformat(start_block["date"]).date()
        st_utc = datetime.combine(d0, time.min, tzinfo=zi).astimezone(UTC)
    else:
        st_utc = datetime.min.replace(tzinfo=UTC)

    if end_block.get("dateTime"):
        et = _parse_iso_maybe_z(end_block["dateTime"])
        if et.tzinfo is None:
            tz = end_block.get("timeZone") or tz_name
            et = et.replace(tzinfo=ZoneInfo(tz))
        et_utc = et.astimezone(UTC)
    elif end_block.get("date"):
        # Google all-day: end.date is exclusive (start of day after last day).
        d1 = datetime.fromisoformat(end_block["date"]).date()
        et_utc = datetime.combine(d1, time.min, tzinfo=zi).astimezone(UTC)
    else:
        et_utc = st_utc + timedelta(days=1)

    if et_utc <= st_utc:
        et_utc = st_utc + timedelta(minutes=1)

    return st_utc, et_utc


def event_overlaps_window(ev: dict[str, Any], window_start: datetime, window_end: datetime, tz_name: str) -> bool:
    """Half-open overlap: [st, et) vs [ws, we) after normalizing to UTC."""

    ws = window_start.astimezone(UTC)
    we = window_end.astimezone(UTC)
    if we <= ws:
        return False
    st, et = event_bounds_utc(ev, tz_name)
    return st < we and et > ws


def list_primary_events(
    time_min: datetime,
    time_max: datetime,
    *,
    tz_name: str | None = None,
) -> list[dict[str, Any]]:
    svc = calendar_service()
    tz = tz_name or calendar_default_timezone()
    req = svc.events().list(
        calendarId="primary",
        timeMin=_format_rfc3339_z(time_min),
        timeMax=_format_rfc3339_z(time_max),
        singleEvents=True,
        orderBy="startTime",
        maxResults=250,
    )
    out: list[dict[str, Any]] = []
    try:
        while req is not None:
            executed = req.execute()
            chunk = executed.get("items") or []
            out.extend(chunk)
            token = executed.get("nextPageToken")
            req = svc.events().list_next(req, executed) if token else None
    except HttpError as e:
        raise RuntimeError(f"Google Calendar API error ({e.status_code}): {e}") from e

    return out


def delete_primary_event(event_id: str) -> None:
    svc = calendar_service()
    try:
        svc.events().delete(calendarId="primary", eventId=event_id).execute()
    except HttpError as e:
        raise RuntimeError(f"Google Calendar API error ({e.status_code}): {e}") from e
