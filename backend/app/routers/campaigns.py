"""
Campaigns Router — Phase 1 stub
Full implementation: Sprint 1 (basic CRUD)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database.session import get_db
from app.database.models import OutreachCampaign, CampaignStatus

router = APIRouter()


# ── Pydantic Schemas ─────────────────────────────────────────
class CampaignCreate(BaseModel):
    name: Optional[str] = None
    domain_target: str
    created_by: Optional[str] = None


class CampaignRead(BaseModel):
    id: str
    name: Optional[str]
    domain_target: str
    status: CampaignStatus
    created_by: Optional[str]
    total_targets: int
    total_drafted: int
    total_sent: int
    total_replied: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────
@router.post("/", response_model=CampaignRead, status_code=201)
async def create_campaign(data: CampaignCreate, db: AsyncSession = Depends(get_db)):
    """Create a new outreach campaign for a given advocacy domain."""
    campaign = OutreachCampaign(
        name=data.name or f"{data.domain_target.title()} Campaign",
        domain_target=data.domain_target.lower().strip(),
        created_by=data.created_by,
    )
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.get("/", response_model=list[CampaignRead])
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    """List all campaigns ordered by most recent first."""
    result = await db.execute(
        select(OutreachCampaign).order_by(OutreachCampaign.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{campaign_id}", response_model=CampaignRead)
async def get_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single campaign by ID."""
    result = await db.execute(
        select(OutreachCampaign).where(OutreachCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a campaign and all its emails (cascade)."""
    result = await db.execute(
        select(OutreachCampaign).where(OutreachCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.delete(campaign)
