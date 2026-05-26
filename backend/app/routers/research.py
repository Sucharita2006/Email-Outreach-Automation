"""
Research Router — Phase 1 stub
Full implementation: Sprint 7 (research orchestrator)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db

router = APIRouter()


@router.post("/company/{company_id}")
async def trigger_company_research(company_id: str, db: AsyncSession = Depends(get_db)):
    """Trigger full research pipeline for a company. Full implementation in Sprint 7."""
    return {"status": "stub", "message": "Sprint 7", "company_id": company_id}


@router.post("/individual/{individual_id}")
async def trigger_individual_research(individual_id: str, db: AsyncSession = Depends(get_db)):
    """Trigger full research pipeline for an individual. Full implementation in Sprint 7."""
    return {"status": "stub", "message": "Sprint 7", "individual_id": individual_id}


@router.post("/batch")
async def trigger_batch_research(target_ids: list[str], db: AsyncSession = Depends(get_db)):
    """Trigger research for a batch of selected targets. Full implementation in Sprint 7."""
    return {"status": "stub", "message": "Sprint 7", "count": len(target_ids)}
