"""
Emails Router — Phase 6
Full implementation of the email generation, review, and export pipeline.

Endpoints:
  POST /emails/generate              — Generate email drafts for selected targets
  POST /emails/generate/single       — Generate one email (individual + company IDs)
  GET  /emails/                      — List email drafts with filters
  GET  /emails/{id}                  — Get single email draft
  PATCH /emails/{id}                 — Edit a draft (human review)
  POST /emails/{id}/approve          — Mark as approved / ready to send
  POST /emails/{id}/regenerate       — Regenerate the draft with the LLM
  GET  /emails/{id}/export           — Export plain text for copy-paste
  GET  /emails/generate/progress/{campaign_id} — SSE real-time progress
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.session import get_db
from app.database.models import (
    Company, Individual, OutreachEmail, OutreachCampaign,
    EmailStatus, TargetType,
)
from app.services import research_orchestrator
from app.config import settings

router = APIRouter()


# ════════════════════════════════════════════════════════════
#  Campaigns CRUD (must be before /{email_id} wildcard routes)
# ════════════════════════════════════════════════════════════

@router.post("/campaigns")
async def create_campaign(
    name: str = Body(...),
    domain_target: str = Body(...),
    created_by: str = Body(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Create an outreach campaign to group a batch of emails."""
    campaign = OutreachCampaign(
        name=name,
        domain_target=domain_target,
        created_by=created_by,
    )
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    await db.commit()
    return {
        "id": campaign.id,
        "name": campaign.name,
        "domain_target": campaign.domain_target,
        "status": campaign.status,
        "created_at": campaign.created_at.isoformat(),
    }


@router.get("/campaigns")
async def list_campaigns(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List all outreach campaigns."""
    stmt = select(OutreachCampaign).order_by(OutreachCampaign.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    campaigns = result.scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "domain_target": c.domain_target,
            "status": c.status,
            "total_drafted": c.total_drafted,
            "total_sent": c.total_sent,
            "total_replied": c.total_replied,
            "created_at": c.created_at.isoformat(),
        }
        for c in campaigns
    ]


class GenerateRequest(BaseModel):
    campaign_id: str
    target_pairs: list[dict]   # [{individual_id, company_id}]
    force_refresh_analysis: bool = False
    concurrency: Optional[int] = None


class SingleGenerateRequest(BaseModel):
    campaign_id: str
    individual_id: str
    company_id: str
    force_refresh_analysis: bool = False


class EmailUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    notes: Optional[str] = None


class EmailRead(BaseModel):
    id: str
    campaign_id: str
    target_type: str
    target_id: str
    recipient_email: Optional[str]
    recipient_name: Optional[str]
    company_name: Optional[str]
    subject: Optional[str]
    body: Optional[str]
    status: str
    drafted_at: Optional[datetime]
    sent_at: Optional[datetime]
    follow_up_due_at: Optional[datetime]
    follow_up_count: int
    llm_model_used: Optional[str]
    notes: Optional[str]
    individual_analysis_snapshot: Optional[dict]
    company_analysis_snapshot: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


# ════════════════════════════════════════════════════════════
#  Generation
# ════════════════════════════════════════════════════════════

@router.post("/generate/single")
async def generate_single_email(
    req: SingleGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate one email draft for a specific individual + company.
    Runs the full 3-call LLM pipeline:
      Call 1: Individual personality + hook analysis
      Call 2: Company mission fit + news hook
      Call 3: Final email draft (subject + body)

    Saves result as an OutreachEmail record in the DB.
    Returns the draft immediately for review.
    """
    # Validate campaign exists
    campaign = await _get_campaign_or_404(req.campaign_id, db)

    # Load individual + company
    individual = await _get_individual_or_404(req.individual_id, db)
    company = await _get_company_or_404(req.company_id, db)

    # Attach company relationship
    individual.company = company

    result = await research_orchestrator.generate_email_for_target(
        individual=individual,
        company=company,
        campaign_id=req.campaign_id,
        db=db,
        force_refresh_analysis=req.force_refresh_analysis,
    )
    await db.commit()

    return result


@router.post("/generate")
async def generate_batch_emails(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate email drafts for multiple targets in one campaign.
    Runs the 3-call pipeline concurrently (respects LLM_BATCH_CONCURRENCY).
    Max 100 targets per call.

    Returns:
        {total, ok, errors, results: [...]}
    """
    if len(req.target_pairs) > 100:
        raise HTTPException(status_code=400, detail="Max 100 targets per batch generation call.")
    if not req.target_pairs:
        raise HTTPException(status_code=400, detail="target_pairs must not be empty.")

    # Validate campaign
    await _get_campaign_or_404(req.campaign_id, db)

    results = await research_orchestrator.batch_generate_emails(
        target_pairs=req.target_pairs,
        campaign_id=req.campaign_id,
        db=db,
        concurrency=req.concurrency,
        force_refresh_analysis=req.force_refresh_analysis,
    )

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    error_count = sum(1 for r in results if r.get("status") not in ("ok", "cached"))

    # Update campaign stats
    campaign = await _get_campaign_or_404(req.campaign_id, db)
    campaign.total_drafted = (campaign.total_drafted or 0) + ok_count
    await db.commit()

    return {
        "campaign_id": req.campaign_id,
        "total": len(results),
        "ok": ok_count,
        "errors": error_count,
        "results": results,
    }


# ════════════════════════════════════════════════════════════
#  CRUD — List, Get, Edit, Approve
# ════════════════════════════════════════════════════════════

@router.get("/", response_model=list[EmailRead])
async def list_emails(
    campaign_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Filter by status: drafted, sent, replied, etc."),
    company_name: Optional[str] = Query(None, description="Filter by company name (contains)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List email drafts with optional filters."""
    stmt = select(OutreachEmail)

    if campaign_id:
        stmt = stmt.where(OutreachEmail.campaign_id == campaign_id)
    if status:
        stmt = stmt.where(OutreachEmail.status == status)
    if company_name:
        stmt = stmt.where(OutreachEmail.company_name.ilike(f"%{company_name}%"))

    stmt = stmt.order_by(OutreachEmail.drafted_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{email_id}", response_model=EmailRead)
async def get_email(email_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single email draft by ID."""
    email = await _get_email_or_404(email_id, db)
    return email


@router.patch("/{email_id}", response_model=EmailRead)
async def update_email(
    email_id: str,
    data: EmailUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Edit a draft email (human review step).
    Allows updating subject, body, and review notes.
    """
    email = await _get_email_or_404(email_id, db)

    if email.status not in (EmailStatus.DRAFTED, EmailStatus.ARCHIVED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit an email with status '{email.status}'. Only 'drafted' emails can be edited."
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(email, field, value)

    await db.flush()
    await db.refresh(email)
    await db.commit()
    return email


@router.post("/{email_id}/approve", response_model=EmailRead)
async def approve_email(
    email_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a draft email as approved/sent by the human reviewer.
    Updates status to 'sent' and records sent timestamp.
    """
    email = await _get_email_or_404(email_id, db)

    if email.status != EmailStatus.DRAFTED:
        raise HTTPException(
            status_code=400,
            detail=f"Email is already '{email.status}'. Only drafted emails can be approved."
        )

    email.status = EmailStatus.SENT
    email.sent_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(email)
    await db.commit()
    return email


@router.post("/{email_id}/regenerate")
async def regenerate_email(
    email_id: str,
    force_refresh_analysis: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate an email draft using the LLM.
    Uses cached analysis unless force_refresh_analysis=True.
    Creates a NEW draft record and archives the old one.
    """
    old_email = await _get_email_or_404(email_id, db)

    # Load individual + company
    individual = await _get_individual_or_404(old_email.target_id, db)
    company_stmt = select(Company).where(Company.name == old_email.company_name)
    comp_result = await db.execute(company_stmt)
    company = comp_result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found for this email.")

    individual.company = company

    # Archive the old draft
    old_email.status = EmailStatus.ARCHIVED
    old_email.archived_at = datetime.now(timezone.utc)
    await db.flush()

    # Generate new draft
    result = await research_orchestrator.generate_email_for_target(
        individual=individual,
        company=company,
        campaign_id=old_email.campaign_id,
        db=db,
        force_refresh_analysis=force_refresh_analysis,
    )
    await db.commit()

    return {**result, "archived_email_id": email_id}


# ════════════════════════════════════════════════════════════
#  Export
# ════════════════════════════════════════════════════════════

@router.get("/{email_id}/export")
async def export_email(
    email_id: str,
    format: str = Query("text", description="Export format: 'text' or 'json'"),
    db: AsyncSession = Depends(get_db),
):
    """
    Export a draft email as plain text (for copy-paste into Gmail/Outlook)
    or as JSON (for programmatic use).
    """
    email = await _get_email_or_404(email_id, db)

    if format == "json":
        return {
            "id": email.id,
            "subject": email.subject,
            "body": email.body,
            "recipient_name": email.recipient_name,
            "recipient_email": email.recipient_email,
            "company_name": email.company_name,
            "status": email.status,
            "drafted_at": email.drafted_at.isoformat() if email.drafted_at else None,
        }

    # Plain text format — ready for copy-paste
    text = f"To: {email.recipient_name} <{email.recipient_email or 'unknown@email.com'}>\n"
    text += f"Subject: {email.subject or 'No subject'}\n"
    text += "-" * 60 + "\n\n"
    text += (email.body or "").strip()
    text += "\n"

    return PlainTextResponse(content=text, media_type="text/plain")


# ════════════════════════════════════════════════════════════
#  SSE Progress Stream
# ════════════════════════════════════════════════════════════

@router.get("/generate/progress/{campaign_id}")
async def generation_progress(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Server-Sent Events endpoint for real-time batch generation progress.
    Streams: drafted_count / total_targets updates.
    Connect from frontend with: new EventSource('/emails/generate/progress/{id}')
    """
    async def _event_stream() -> AsyncGenerator[str, None]:
        # Poll the DB every 2 seconds for new drafted emails
        last_count = 0
        max_polls = 150  # 5 min timeout (150 × 2s)

        for _ in range(max_polls):
            count_result = await db.execute(
                select(func.count()).select_from(OutreachEmail).where(
                    OutreachEmail.campaign_id == campaign_id,
                    OutreachEmail.status == EmailStatus.DRAFTED,
                )
            )
            count = count_result.scalar_one()

            if count != last_count:
                event_data = json.dumps({"drafted": count, "campaign_id": campaign_id})
                yield f"data: {event_data}\n\n"
                last_count = count

            await asyncio.sleep(2)

        yield "data: {\"status\": \"timeout\"}\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


# ════════════════════════════════════════════════════════════
#  Campaigns CRUD (lightweight — for grouping email batches)
# ════════════════════════════════════════════════════════════

@router.post("/campaigns")
async def create_campaign(
    name: str = Body(...),
    domain_target: str = Body(...),
    created_by: str = Body(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Create an outreach campaign to group a batch of emails."""
    campaign = OutreachCampaign(
        name=name,
        domain_target=domain_target,
        created_by=created_by,
    )
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    await db.commit()
    return {
        "id": campaign.id,
        "name": campaign.name,
        "domain_target": campaign.domain_target,
        "status": campaign.status,
        "created_at": campaign.created_at.isoformat(),
    }


@router.get("/campaigns")
async def list_campaigns(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List all outreach campaigns."""
    stmt = select(OutreachCampaign).order_by(OutreachCampaign.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    campaigns = result.scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "domain_target": c.domain_target,
            "status": c.status,
            "total_drafted": c.total_drafted,
            "total_sent": c.total_sent,
            "total_replied": c.total_replied,
            "created_at": c.created_at.isoformat(),
        }
        for c in campaigns
    ]


# ════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════

async def _get_email_or_404(email_id: str, db: AsyncSession) -> OutreachEmail:
    result = await db.execute(select(OutreachEmail).where(OutreachEmail.id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


async def _get_campaign_or_404(campaign_id: str, db: AsyncSession) -> OutreachCampaign:
    result = await db.execute(select(OutreachCampaign).where(OutreachCampaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


async def _get_individual_or_404(individual_id: str, db: AsyncSession) -> Individual:
    result = await db.execute(select(Individual).where(Individual.id == individual_id))
    individual = result.scalar_one_or_none()
    if not individual:
        raise HTTPException(status_code=404, detail="Individual not found")
    return individual


async def _get_company_or_404(company_id: str, db: AsyncSession) -> Company:
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
