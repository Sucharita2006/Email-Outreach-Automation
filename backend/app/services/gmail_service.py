"""
Gmail API Service — Phase 7
Creates Gmail draft emails and manages OAuth 2.0 authentication.

Provides:
  - OAuth 2.0 flow (authorization URL + callback token exchange)
  - Create Gmail draft from email record
  - List/fetch drafts
  - Token refresh (auto-handled by google-auth library)

Requires in .env:
  GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REDIRECT_URI

Dependencies:
  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

NOTE: OAuth tokens are stored in-memory for the MVP. Production should
persist them encrypted in the database.
"""

import base64
import json
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

from app.config import settings

from app.database.session import AsyncSessionLocal
from app.database.models import SystemSetting
from sqlalchemy import select

# ── Database-based token store (persists across container restarts) ─────
_token_store: dict = {}  # runtime cache
_token_store_loaded = False


async def _load_token_store():
    """Load token store from database if not loaded yet."""
    global _token_store, _token_store_loaded
    if _token_store_loaded:
        return
    _token_store_loaded = True
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == "gmail_tokens"))
        setting = result.scalar_one_or_none()
        if setting:
            _token_store["credentials"] = setting.value


async def _save_token_store():
    """Persist credentials to database."""
    creds = _token_store.get("credentials")
    if creds:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SystemSetting).where(SystemSetting.key == "gmail_tokens"))
            setting = result.scalar_one_or_none()
            if setting:
                setting.value = creds
            else:
                setting = SystemSetting(key="gmail_tokens", value=creds)
                db.add(setting)
            await db.commit()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",  # Create drafts
    "https://www.googleapis.com/auth/gmail.readonly",  # Read inbox for replies
]


def is_configured() -> bool:
    """Check if Gmail OAuth credentials are set in .env."""
    return bool(settings.GMAIL_CLIENT_ID and settings.GMAIL_CLIENT_SECRET)



def get_authorization_url() -> dict:
    """
    Generate the Gmail OAuth 2.0 authorization URL.
    User must visit this URL to grant access.
    Returns: {url, state}
    """
    if not is_configured():
        return {
            "status": "not_configured",
            "message": "GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET must be set in .env",
        }

    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": settings.GMAIL_CLIENT_ID,
                    "client_secret": settings.GMAIL_CLIENT_SECRET,
                    "redirect_uris": [settings.GMAIL_REDIRECT_URI],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
        )
        flow.redirect_uri = settings.GMAIL_REDIRECT_URI
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        # Store flow for callback (MVP: in-memory)
        _token_store["_flow_state"] = state
        _token_store["_flow"] = flow
        return {"status": "ok", "url": auth_url, "state": state}
    except ImportError:
        return {
            "status": "library_missing",
            "message": "Install: pip install google-auth-oauthlib google-api-python-client",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def handle_oauth_callback(code: str, state: str) -> dict:
    """
    Handle the OAuth callback and exchange code for tokens.
    Called from the /auth/gmail/callback endpoint.
    """
    flow = _token_store.get("_flow")
    if not flow:
        return {"status": "error", "message": "No OAuth flow in progress. Start from /auth/gmail/authorize"}

    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        _token_store["credentials"] = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or SCOPES),
        }
        await _save_token_store()  # persist to db
        return {
            "status": "ok",
            "message": "Gmail OAuth successful. You can now create drafts.",
            "has_refresh_token": bool(creds.refresh_token),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _get_gmail_service():
    """
    Build and return an authenticated Gmail API service.
    Raises RuntimeError if not authenticated.
    """
    await _load_token_store()
    if "credentials" not in _token_store:
        raise RuntimeError("Gmail not authenticated. Visit /auth/gmail/authorize first.")

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds_data = _token_store["credentials"]
        creds = Credentials(
            token=creds_data["token"],
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=creds_data.get("client_id", settings.GMAIL_CLIENT_ID),
            client_secret=creds_data.get("client_secret", settings.GMAIL_CLIENT_SECRET),
            scopes=creds_data.get("scopes", SCOPES),
        )
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        # If token was refreshed, persist the new one
        if creds.token != creds_data["token"]:
            _token_store["credentials"]["token"] = creds.token
            await _save_token_store()
        return service
    except ImportError:
        raise RuntimeError("Install: pip install google-api-python-client google-auth")


async def disconnect() -> bool:
    """Disconnect Gmail by removing tokens from the database and cache."""
    await _load_token_store()
    _token_store.pop("credentials", None)
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == "gmail_tokens"))
        setting = result.scalar_one_or_none()
        if setting:
            await db.delete(setting)
            await db.commit()
    return True


async def is_authenticated() -> bool:
    """Return True if Gmail OAuth tokens are available."""
    await _load_token_store()
    return "credentials" in _token_store


def _build_mime_message(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    from_name: str = None,
    reply_to: str = None,
) -> str:
    """Build a MIME email message and return it base64url-encoded."""
    msg = MIMEMultipart("alternative")
    msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email
    msg["Subject"] = subject
    if from_name:
        msg["From"] = from_name
    if reply_to:
        msg["Reply-To"] = reply_to

    # Plain text part
    text_part = MIMEText(body, "plain", "utf-8")
    msg.attach(text_part)

    # HTML part (simple formatting)
    html_body = body.replace("\n\n", "</p><p>").replace("\n", "<br>")
    html_body = f"<p>{html_body}</p>"
    html_part = MIMEText(html_body, "html", "utf-8")
    msg.attach(html_part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw


async def create_draft(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
) -> dict:
    """
    Create a Gmail draft (does NOT send — human reviews first).

    Returns:
        {status, draft_id, gmail_link}
    """
    if not await is_authenticated():
        return {
            "status": "not_authenticated",
            "message": "Gmail OAuth required. Visit /auth/gmail/authorize",
        }

    if not to_email or not subject or not body:
        return {"status": "error", "message": "to_email, subject, and body are required."}

    try:
        service = await _get_gmail_service()
        raw_message = _build_mime_message(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            body=body,
            from_name=settings.NONPROFIT_SENDER_NAME,
        )
        draft = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": raw_message}},
        ).execute()

        draft_id = draft.get("id")
        return {
            "status": "ok",
            "draft_id": draft_id,
            "gmail_link": f"https://mail.google.com/mail/u/0/#drafts/{draft_id}",
        }
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Gmail API error: {str(e)[:200]}"}


async def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
) -> dict:
    """
    Send an email directly through the Gmail API, bypassing the Drafts folder.

    Returns:
        {status, message_id}
    """
    if not await is_authenticated():
        return {
            "status": "not_authenticated",
            "message": "Gmail OAuth required. Visit /auth/gmail/authorize",
        }

    if not to_email or not subject or not body:
        return {"status": "error", "message": "to_email, subject, and body are required."}

    try:
        service = await _get_gmail_service()
        raw_message = _build_mime_message(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            body=body,
            from_name=settings.NONPROFIT_SENDER_NAME,
        )
        msg = service.users().messages().send(
            userId="me",
            body={"raw": raw_message},
        ).execute()

        return {
            "status": "ok",
            "message_id": msg.get("id"),
        }
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Gmail API error: {str(e)[:200]}"}


async def list_drafts(max_results: int = 10) -> dict:
    """List recent Gmail drafts created by this app."""
    if not await is_authenticated():
        return {"status": "not_authenticated", "drafts": []}

    try:
        service = await _get_gmail_service()
        result = service.users().drafts().list(userId="me", maxResults=max_results).execute()
        return {"status": "ok", "drafts": result.get("drafts", []), "total": result.get("resultSizeEstimate", 0)}
    except Exception as e:
        return {"status": "error", "message": str(e), "drafts": []}


async def check_inbox_for_replies(
    sent_subjects: list[str],
    since_days: int = 30,
) -> list[dict]:
    """
    Poll Gmail inbox for replies matching any of the given subjects.
    Used by the reply tracker to auto-detect responses.

    Returns list of {thread_id, subject, sender, snippet, body, received_at}
    """
    if not await is_authenticated():
        return []

    try:
        service = await _get_gmail_service()
        from datetime import datetime, timedelta, timezone
        since_date = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=since_days)).strftime("%Y/%m/%d")

        seen_ids = set()
        replies = []
        for subject in sent_subjects[:50]:  # Check up to 50
            safe_subject = subject.replace('"', '').replace("'", "")
            # Build query: inbox messages matching our subject since date
            query = f"in:inbox subject:\"{safe_subject}\" after:{since_date}"
            result = service.users().messages().list(
                userId="me", q=query, maxResults=5
            ).execute()

            for msg_ref in result.get("messages", []):
                msg_id = msg_ref["id"]
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                # Fetch full message to get body text
                msg = service.users().messages().get(
                    userId="me", id=msg_id, format="full"
                ).execute()
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                body_text = _extract_body_text(msg.get("payload", {}))

                replies.append({
                    "thread_id": msg.get("threadId"),
                    "message_id": msg_id,
                    "subject": headers.get("Subject", ""),
                    "sender": headers.get("From", ""),
                    "snippet": msg.get("snippet", "")[:200],
                    "body": body_text,
                    "received_at": headers.get("Date", ""),
                })

        return replies
    except Exception as e:
        import traceback
        traceback.print_exc()
        return []


def _extract_body_text(payload: dict) -> str:
    """
    Recursively extract plain-text body from a Gmail message payload.
    Falls back to HTML → stripped text if no plain part found.
    """
    if not payload:
        return ""

    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    # Single-part message
    if body_data and mime_type == "text/plain":
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    # Multipart — recurse into parts
    parts = payload.get("parts", [])
    plain_text = ""
    html_text = ""
    for part in parts:
        part_mime = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data")
        if part_mime == "text/plain" and part_data:
            plain_text += base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
        elif part_mime == "text/html" and part_data:
            html_text += base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
        elif part.get("parts"):
            # Nested multipart (e.g. multipart/alternative inside multipart/mixed)
            nested = _extract_body_text(part)
            if nested:
                plain_text += nested

    if plain_text:
        return plain_text.strip()

    # Fallback: strip HTML tags for a rough text version
    if html_text:
        text = re.sub(r'<style[^>]*>.*?</style>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:2000]

    # Last resort: decode whatever body data is there
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace").strip()

    return ""
