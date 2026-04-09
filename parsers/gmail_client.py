"""
Gmail API wrapper — shared by sgi_parser, kraken_parser, billing_cross_check.

Auth model:
  - One-time interactive flow produces a refresh token (run with --first-time-auth).
  - Refresh token is stored as a GitHub Actions secret: GMAIL_REFRESH_TOKEN.
  - In Actions, env vars GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN
    are used to mint an access token non-interactively.

Scopes: gmail.readonly (we never send or modify).
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from dataclasses import dataclass
from typing import Iterable, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@dataclass
class GmailMessage:
    id: str
    thread_id: str
    subject: str
    sender: str
    date: str
    snippet: str
    body_html: Optional[str]
    body_text: Optional[str]
    attachments: list[dict]  # [{filename, mime_type, attachment_id, size}]


def _creds_from_env() -> Credentials:
    client_id = os.environ["GMAIL_CLIENT_ID"]
    client_secret = os.environ["GMAIL_CLIENT_SECRET"]
    refresh_token = os.environ["GMAIL_REFRESH_TOKEN"]

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def get_service():
    """Return an authenticated Gmail API service client."""
    creds = _creds_from_env()
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def search_messages(service, query: str, max_results: int = 25) -> list[str]:
    """Return message IDs matching the Gmail search query."""
    resp = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    return [m["id"] for m in resp.get("messages", [])]


def _decode_body(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def _walk_parts(parts: Iterable[dict], out: dict) -> None:
    for p in parts:
        mime = p.get("mimeType", "")
        body = p.get("body", {})
        if mime == "text/html" and body.get("data"):
            out["body_html"] = _decode_body(body["data"])
        elif mime == "text/plain" and body.get("data"):
            out["body_text"] = _decode_body(body["data"])
        elif body.get("attachmentId"):
            out["attachments"].append({
                "filename": p.get("filename", ""),
                "mime_type": mime,
                "attachment_id": body["attachmentId"],
                "size": body.get("size", 0),
            })
        if p.get("parts"):
            _walk_parts(p["parts"], out)


def get_message(service, msg_id: str) -> GmailMessage:
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    out = {"body_html": None, "body_text": None, "attachments": []}

    payload = msg["payload"]
    if payload.get("parts"):
        _walk_parts(payload["parts"], out)
    else:
        body = payload.get("body", {})
        if body.get("data"):
            mime = payload.get("mimeType", "")
            if mime == "text/html":
                out["body_html"] = _decode_body(body["data"])
            else:
                out["body_text"] = _decode_body(body["data"])

    return GmailMessage(
        id=msg["id"],
        thread_id=msg["threadId"],
        subject=headers.get("subject", ""),
        sender=headers.get("from", ""),
        date=headers.get("date", ""),
        snippet=msg.get("snippet", ""),
        body_html=out["body_html"],
        body_text=out["body_text"],
        attachments=out["attachments"],
    )


def download_attachment(service, msg_id: str, attachment_id: str) -> bytes:
    att = service.users().messages().attachments().get(
        userId="me", messageId=msg_id, id=attachment_id
    ).execute()
    return base64.urlsafe_b64decode(att["data"].encode("utf-8"))


# ---------------------------------------------------------------------------
# One-time interactive auth (run locally, not in Actions)
# ---------------------------------------------------------------------------

def first_time_auth(client_secrets_path: str) -> None:
    """Interactive flow — prints the refresh token to paste into repo secrets."""
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
    creds = flow.run_local_server(port=0)
    print("\n=== PASTE THESE INTO GITHUB REPO SECRETS ===")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("============================================\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--first-time-auth", action="store_true")
    ap.add_argument("--client-secrets", default="client_secrets.json")
    args = ap.parse_args()

    if args.first_time_auth:
        if not os.path.exists(args.client_secrets):
            print(f"Missing {args.client_secrets}. Download OAuth client JSON "
                  "from Google Cloud Console → Credentials.", file=sys.stderr)
            sys.exit(1)
        first_time_auth(args.client_secrets)
    else:
        # smoke test
        svc = get_service()
        ids = search_messages(svc, "from:SGI_Reporting@lnw.com newer_than:3d", max_results=3)
        print(f"Found {len(ids)} recent SGI messages.")
