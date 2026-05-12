#!/usr/bin/env python3
"""One-shot OAuth for Google Calendar using a **Web application** OAuth client.

Use this when your Google Cloud OAuth client type is **網頁應用程式** (not Desktop).

Prerequisites:
- Enable Calendar API; OAuth consent screen includes calendar.events scope.
- Create OAuth client **Web application**.
- Under Authorized redirect URIs, add **exactly**:

    http://127.0.0.1:8088/oauth2callback

  If port 8088 is busy: use `--port 8090` and register e.g.
  http://127.0.0.1:8090/oauth2callback

.env:

  GOOGLE_CALENDAR_CLIENT_ID=...
  GOOGLE_CALENDAR_CLIENT_SECRET=...

Run:

  cd backend && python scripts/oauth_google_calendar_web.py

This script sets OAUTHLIB_INSECURE_TRANSPORT for http://127.0.0.1 redirects only
(local token exchange). Override in your shell if needed.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
DEFAULT_REDIRECT_PORT = 8088
REDIRECT_PATH = "/oauth2callback"


def _redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}{REDIRECT_PATH}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Calendar OAuth (Web application client).")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("GOOGLE_OAUTH_WEB_REDIRECT_PORT") or DEFAULT_REDIRECT_PORT),
        help=f"Local port for OAuth callback (default: {DEFAULT_REDIRECT_PORT})",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the authorize URL only; do not open a browser.",
    )
    args = parser.parse_args()

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

    redirect_uri = _redirect_uri(args.port)
    if redirect_uri.startswith(("http://127.0.0.1:", "http://localhost:")):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    authorization_url, expected_state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )

    print(
        "\nRegister this redirect URI on your **Web application** OAuth client:\n"
        f"  {redirect_uri}\n",
        file=sys.stderr,
    )

    class OAuthHTTPServer(HTTPServer):
        def __init__(
            self,
            server_address: tuple[str, int],
            RequestHandlerClass: type[BaseHTTPRequestHandler],
            *,
            expected_state: str,
        ):
            super().__init__(server_address, RequestHandlerClass)
            self.expected_state = expected_state
            self.credentials = None
            self.oauth_fatal: str | None = None

    class OAuthHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            srv = self.server
            assert isinstance(srv, OAuthHTTPServer)
            parsed = urlparse(self.path)
            if parsed.path != REDIRECT_PATH:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Not found")
                threading.Thread(target=srv.shutdown).start()
                return

            qs = parse_qs(parsed.query)
            if qs.get("error"):
                err = qs.get("error", ["unknown"])[0]
                desc = (qs.get("error_description") or [""])[0]
                srv.oauth_fatal = f"{err}: {desc}"
                self._html(400, "<p>Authorization failed. You may close this tab.</p>")
                threading.Thread(target=srv.shutdown).start()
                return

            code = (qs.get("code") or [None])[0]
            state = (qs.get("state") or [None])[0]
            if not code or state != srv.expected_state:
                srv.oauth_fatal = "missing code or state mismatch"
                self._html(400, "<p>Invalid callback. You may close this tab.</p>")
                threading.Thread(target=srv.shutdown).start()
                return

            authorization_response = f"{redirect_uri}?{parsed.query}"
            try:
                flow.fetch_token(authorization_response=authorization_response)
            except Exception as e:
                srv.oauth_fatal = str(e)
                self._html(
                    500,
                    "<p>Token exchange failed. Check terminal output. You may close this tab.</p>",
                )
                threading.Thread(target=srv.shutdown).start()
                return

            srv.credentials = flow.credentials
            self._html(200, "<p>Success. You can close this tab and return to the terminal.</p>")
            threading.Thread(target=srv.shutdown).start()

        def _html(self, status: int, body: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"<html><meta charset=utf-8><body>{body}</body></html>".encode("utf-8")
            )

    try:
        server = OAuthHTTPServer(
            ("127.0.0.1", args.port),
            OAuthHandler,
            expected_state=expected_state,
        )
    except OSError as e:
        print(f"Cannot bind 127.0.0.1:{args.port}: {e}", file=sys.stderr)
        print(
            "Choose another port: python scripts/oauth_google_calendar_web.py --port 8090\n"
            "and add the matching redirect URI in Google Cloud Console.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Opening browser (or visit URL manually):\n", authorization_url, "\n", sep="", flush=True)
    if not args.no_browser:
        webbrowser.open(authorization_url, new=1)

    try:
        server.serve_forever()
    finally:
        server.server_close()

    if server.oauth_fatal:
        print(f"\nOAuth failed: {server.oauth_fatal}\n", file=sys.stderr)
        sys.exit(1)

    creds = server.credentials
    if not creds or not getattr(creds, "refresh_token", None):
        print(
            "No refresh_token in response. Revoke app access at "
            "https://myaccount.google.com/permissions and run again "
            "(this script uses prompt=consent).",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\nAdd to your .env (do not commit):\n")
    print(f"GOOGLE_CALENDAR_REFRESH_TOKEN={creds.refresh_token}\n")


if __name__ == "__main__":
    main()