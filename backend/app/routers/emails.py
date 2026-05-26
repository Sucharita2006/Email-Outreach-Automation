"""
Emails Router — Phase 1 stub
Full implementation: Sprint 8–9 (LLM generation + review)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db

router = APIRouter()


@router.post("/generate")
async def generate_emails(
    campaign_id: str = Query(...),
    target_ids: list[str] = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger LLM email generation for selected targets in a campaign.
    Uses 3-call architecture: Individual Analysis → Company Analysis → Email Draft.
    Full implementation in Sprint 8–9.
    """
    return {"status": "stub", "message": "Sprint 8-9", "campaign_id": campaign_id}


@router.get("/")
async def list_emails(
    campaign_id: str = Query(None),
    status: str = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List email drafts, optionally filtered by campaign or status. Sprint 9."""
    return {"status": "stub", "message": "Sprint 9"}


@router.patch("/{email_id}")
async def update_email(email_id: str, db: AsyncSession = Depends(get_db)):
    """Update (edit) a draft email. Sprint 10."""
    return {"status": "stub", "message": "Sprint 10", "email_id": email_id}


@router.post("/{email_id}/approve")
async def approve_email(email_id: str, db: AsyncSession = Depends(get_db)):
    """Mark an email as approved / sent by human. Sprint 10."""
    return {"status": "stub", "message": "Sprint 10", "email_id": email_id}


@router.get("/{email_id}/export")
async def export_email(email_id: str, db: AsyncSession = Depends(get_db)):
    """Export a draft as plain text for copy-paste. Sprint 11."""
    return {"status": "stub", "message": "Sprint 11", "email_id": email_id}


@router.get("/generate/progress/{campaign_id}")
async def generation_progress(campaign_id: str):
    """
    Server-Sent Events (SSE) endpoint for real-time batch generation progress.
    e.g., '12/100 drafts generated'. Full implementation in Sprint 9.
    """
    return {"status": "stub", "message": "Sprint 9 — SSE endpoint"}
