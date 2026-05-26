"""
Tracking Router — Phase 1 stub
Full implementation: Sprint 12 (reply tracking), Sprint 14 (Gmail polling)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db

router = APIRouter()


@router.post("/{email_id}/mark-replied")
async def mark_replied(
    email_id: str,
    reply_snippet: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually mark an outreach email as replied.
    Sets status=replied, known=True on target, logs to reply_history.
    Full implementation in Sprint 12.
    """
    return {"status": "stub", "message": "Sprint 12", "email_id": email_id}


@router.post("/{email_id}/mark-ignored")
async def mark_ignored(email_id: str, db: AsyncSession = Depends(get_db)):
    """
    Manually mark an outreach email as ignored.
    Schedules follow-up based on FOLLOWUP_1_DAYS config.
    Full implementation in Sprint 12.
    """
    return {"status": "stub", "message": "Sprint 12", "email_id": email_id}


@router.get("/dashboard")
async def tracking_dashboard(
    campaign_id: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns aggregate reply/ignore/pending stats per campaign.
    Full implementation in Sprint 12.
    """
    return {"status": "stub", "message": "Sprint 12"}


@router.post("/poll-gmail")
async def poll_gmail_replies(db: AsyncSession = Depends(get_db)):
    """
    Trigger a manual Gmail inbox poll to detect new replies.
    Auto-classification by matching sender + thread subject.
    Full implementation in Sprint 14.
    """
    return {"status": "stub", "message": "Sprint 14"}
