#!/usr/bin/env python3
"""One-shot OAuth for Google Calendar (Desktop client). Prints refresh token for .env.

Prerequisites (Google Cloud Console):
- Create a project, enable Calendar API.
- OAuth consent screen (add yourself as test user if external).
- Create OAuth client **Desktop app**; copy Client ID and Client Secret into .env:

  GOOGLE_CALENDAR_CLIENT_ID=...
  GOOGLE_CALENDAR_CLIENT_SECRET=...

Then from repo root or backend:

  cd backend && python scripts/oauth_google_calendar.py

Paste the printed GOOGLE_CALENDAR_REFRESH_TOKEN=... into .env (never commit).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    load_dotenv(repo_root / ".env")
    load_dotenv(backend_root / ".env")

    client_id = (os.environ.get("GOOGLE_CALENDAR_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        print(
            "Missing GOOGLE_CALENDAR_CLIENT_ID or GOOGLE_CALENDAR_CLIENT_SECRET in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    refresh = getattr(creds, "refresh_token", None)
    if not refresh:
        print(
            "No refresh_token in response. Try revoking app access at "
            "https://myaccount.google.com/permissions or use a Desktop OAuth client.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("\nAdd to your .env (do not commit):\n")
    print(f"GOOGLE_CALENDAR_REFRESH_TOKEN={refresh}\n")


if __name__ == "__main__":
    main()
