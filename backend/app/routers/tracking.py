"""
Tracking Router — Phase 7: Full implementation
Reply tracking, follow-up management, Gmail integration, and dashboard.

Endpoints:
  POST /tracking/{email_id}/mark-replied     — Mark email as replied
  POST /tracking/{email_id}/mark-ignored     — Mark as ignored + schedule follow-up
  POST /tracking/{email_id}/push-to-gmail    — Push draft to Gmail
  POST /tracking/{email_id}/schedule-followup — Manually schedule follow-up
  POST /tracking/process-follow-ups          — Run batch follow-up processor
  GET  /tracking/follow-ups/due              — List emails due for follow-up
  GET  /tracking/reply-history/{target_id}   — Full reply history for a target
  GET  /tracking/dashboard                   — Aggregate campaign stats
  GET  /auth/gmail/status                    — Gmail auth status
  GET  /auth/gmail/authorize                 — Get Gmail OAuth URL
  GET  /auth/gmail/callback                  — Handle OAuth callback
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.session import get_db
from app.database.models import OutreachEmail, EmailStatus
from app.services import tracker_service, followup_service, gmail_service

router = APIRouter()


# ════════════════════════════════════════════════════════════
#  Reply Tracking
# ════════════════════════════════════════════════════════════

class MarkRepliedRequest(BaseModel):
    reply_snippet: str = ""
    sentiment: str = "neutral"   # "positive", "neutral", "negative"


@router.post("/{email_id}/mark-replied")
async def mark_replied(
    email_id: str,
    req: MarkRepliedRequest = Body(default=MarkRepliedRequest()),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark an outreach email as replied.
    - Updates status → 'replied'
    - Creates a ReplyHistory record
    - Marks the individual/company as 'known' (won't be targeted again)
    - Cancels any pending follow-up
    """
    email = await _get_email_or_404(email_id, db)

    if email.status == EmailStatus.REPLIED:
        return {"status": "already_replied", "email_id": email_id}

    result = await tracker_service.mark_replied(
        email=email,
        db=db,
        reply_snippet=req.reply_snippet,
        sentiment=req.sentiment,
    )
    # Cancel any pending follow-up
    email.follow_up_due_at = None
    await db.commit()
    return result


@router.post("/{email_id}/mark-ignored")
async def mark_ignored(
    email_id: str,
    schedule_follow_up: bool = Query(True, description="Automatically schedule a follow-up"),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark an outreach email as ignored (no reply).
    Optionally schedules a follow-up after FOLLOWUP_1_DAYS days.
    """
    email = await _get_email_or_404(email_id, db)

    if email.status in (EmailStatus.REPLIED, EmailStatus.IGNORED):
        return {
            "status": "already_marked",
            "current_status": email.status,
            "email_id": email_id,
        }

    result = await tracker_service.mark_ignored(
        email=email,
        db=db,
        schedule_follow_up=schedule_follow_up,
    )
    await db.commit()
    return result


@router.post("/{email_id}/schedule-followup")
async def schedule_follow_up(
    email_id: str,
    days: Optional[int] = Query(None, description="Days from now (default: FOLLOWUP_1_DAYS setting)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually set a follow-up due date for an email.
    Useful for overriding the default follow-up schedule.
    """
    email = await _get_email_or_404(email_id, db)
    result = await followup_service.schedule_follow_up(email, db, days=days)
    await db.commit()
    return result


# ════════════════════════════════════════════════════════════
#  Follow-up Processing
# ════════════════════════════════════════════════════════════

@router.post("/process-follow-ups")
async def process_follow_ups(
    campaign_id: Optional[str] = Query(None),
    push_to_gmail: bool = Query(False, description="Also create Gmail drafts"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Run the follow-up processor:
    1. Find all emails due for a follow-up
    2. Generate LLM follow-up drafts (using followup.j2)
    3. Save new OutreachEmail records with status 'drafted'
    4. Optionally push drafts to Gmail

    Safe to run repeatedly — only processes emails that are actually due.
    """
    result = await followup_service.process_due_follow_ups(
        db=db,
        campaign_id=campaign_id,
        push_to_gmail=push_to_gmail,
        limit=limit,
    )
    return result


@router.get("/follow-ups/due")
async def list_due_follow_ups(
    campaign_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    List all emails currently due for a follow-up.
    Useful for reviewing before running the follow-up processor.
    """
    due_emails = await tracker_service.get_due_follow_ups(db)

    if campaign_id:
        due_emails = [e for e in due_emails if e.campaign_id == campaign_id]

    return {
        "count": len(due_emails),
        "emails": [
            {
                "email_id": e.id,
                "campaign_id": e.campaign_id,
                "recipient_name": e.recipient_name,
                "recipient_email": e.recipient_email,
                "company_name": e.company_name,
                "subject": e.subject,
                "status": e.status,
                "sent_at": e.sent_at.isoformat() if e.sent_at else None,
                "follow_up_due_at": e.follow_up_due_at.isoformat() if e.follow_up_due_at else None,
                "follow_up_count": e.follow_up_count,
            }
            for e in due_emails
        ],
    }


# ════════════════════════════════════════════════════════════
#  Reply History
# ════════════════════════════════════════════════════════════

@router.get("/reply-history/{target_id}")
async def get_reply_history(target_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the full reply history for a target (individual or company).
    Returns all recorded replies in reverse chronological order.
    """
    history = await tracker_service.get_reply_history(target_id, db)
    return {"target_id": target_id, "reply_count": len(history), "history": history}


# ════════════════════════════════════════════════════════════
#  Dashboard
# ════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def tracking_dashboard(
    campaign_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns aggregate stats for the tracking dashboard:
    - Totals per status (drafted, sent, replied, ignored, follow-up sent)
    - Reply rate %
    - Follow-ups due now
    - Pending review count
    """
    return await tracker_service.tracking_dashboard(campaign_id, db)


# ════════════════════════════════════════════════════════════
#  Gmail Integration
# ════════════════════════════════════════════════════════════

@router.post("/{email_id}/push-to-gmail")
async def push_to_gmail(
    email_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Push an email draft to Gmail as a Gmail Draft.
    The human reviewer can then open Gmail, review, and send manually.
    Requires: Gmail OAuth (visit /auth/gmail/authorize first).
    """
    email = await _get_email_or_404(email_id, db)

    if not email.subject or not email.body:
        raise HTTPException(status_code=400, detail="Email has no subject or body to push.")
    if not email.recipient_email:
        raise HTTPException(status_code=400, detail="Email has no recipient email address.")

    result = await gmail_service.create_draft(
        to_email=email.recipient_email,
        to_name=email.recipient_name or "",
        subject=email.subject,
        body=email.body,
    )

    if result.get("status") == "ok":
        email.gmail_draft_id = result.get("draft_id")
        await db.flush()
        await db.commit()

    return {**result, "email_id": email_id}


@router.get("/auth/gmail/status")
async def gmail_auth_status():
    """Check whether Gmail OAuth credentials are configured and authenticated."""
    return {
        "configured": gmail_service.is_configured(),
        "authenticated": gmail_service.is_authenticated(),
        "message": (
            "Ready to push drafts to Gmail."
            if gmail_service.is_authenticated()
            else "Visit /tracking/auth/gmail/authorize to connect Gmail."
        ),
    }


@router.get("/auth/gmail/authorize")
async def gmail_authorize():
    """
    Get the Gmail OAuth 2.0 authorization URL.
    User must open this URL in a browser and grant access.
    """
    result = gmail_service.get_authorization_url()
    return result


@router.get("/auth/gmail/callback")
async def gmail_callback(
    code: str = Query(...),
    state: str = Query(""),
):
    """
    Handle the Gmail OAuth callback after user grants access.
    Exchange authorization code for access + refresh tokens.
    """
    result = gmail_service.handle_oauth_callback(code=code, state=state)
    return result


@router.post("/poll-gmail")
async def poll_gmail_replies(
    campaign_id: Optional[str] = Query(None),
    since_days: int = Query(30),
    db: AsyncSession = Depends(get_db),
):
    """
    Poll Gmail inbox to automatically detect replies.
    Matches inbox messages against sent email subjects.
    Marks matching emails as replied in the DB.
    Requires: Gmail OAuth authentication.
    """
    if not gmail_service.is_authenticated():
        return {
            "status": "not_authenticated",
            "message": "Visit /tracking/auth/gmail/authorize to connect Gmail first.",
        }

    # Fetch sent emails to check against
    stmt = select(OutreachEmail).where(
        OutreachEmail.status.in_([EmailStatus.SENT, EmailStatus.FOLLOW_UP_SENT, EmailStatus.IGNORED])
    )
    if campaign_id:
        stmt = stmt.where(OutreachEmail.campaign_id == campaign_id)
    result = await db.execute(stmt)
    sent_emails = result.scalars().all()

    if not sent_emails:
        return {"status": "ok", "message": "No sent emails to check.", "new_replies": 0}

    # Get subjects for inbox matching
    subjects = [e.subject for e in sent_emails if e.subject]
    inbox_replies = await gmail_service.check_inbox_for_replies(subjects, since_days=since_days)

    # Match inbox replies to our sent emails
    new_replies = 0
    reply_details = []

    for reply in inbox_replies:
        reply_subject = reply.get("subject", "")
        # Match "Re: {original subject}"
        original_subject = reply_subject.replace("Re: ", "").replace("RE: ", "").strip()
        matched_email = next(
            (e for e in sent_emails if e.subject and e.subject.strip() == original_subject),
            None
        )
        if matched_email and matched_email.status != EmailStatus.REPLIED:
            await tracker_service.mark_replied(
                email=matched_email,
                db=db,
                reply_snippet=reply.get("snippet", ""),
                sentiment="neutral",
            )
            new_replies += 1
            reply_details.append({
                "email_id": matched_email.id,
                "subject": original_subject,
                "sender": reply.get("sender"),
            })

    await db.commit()

    return {
        "status": "ok",
        "inbox_replies_found": len(inbox_replies),
        "new_replies_matched": new_replies,
        "replies": reply_details,
    }


# ════════════════════════════════════════════════════════════
#  Helper
# ════════════════════════════════════════════════════════════

async def _get_email_or_404(email_id: str, db: AsyncSession) -> OutreachEmail:
    result = await db.execute(select(OutreachEmail).where(OutreachEmail.id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email
