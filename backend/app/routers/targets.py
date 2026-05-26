"""
Targets Router — Phase 1 stub
Full implementation: Sprint 2 (fuzzy domain search + selection)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db

router = APIRouter()


@router.get("/search")
async def search_targets(
    domain: str = Query(..., description="Advocacy domain keyword, e.g. 'veganism'"),
    include_known: bool = Query(True, description="Include previously contacted targets"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search companies and individuals by advocacy domain keyword.
    Returns fuzzy-matched results from the internal database.
    Full implementation in Sprint 2.
    """
    return {
        "status": "stub",
        "message": "Target search will be implemented in Sprint 2",
        "query": domain,
    }


@router.get("/companies")
async def list_companies(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List all companies. Full implementation in Sprint 2."""
    return {"status": "stub", "message": "Sprint 2"}


@router.get("/individuals")
async def list_individuals(
    company_id: str = Query(None, description="Filter by company ID"),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List individuals, optionally filtered by company. Full implementation in Sprint 2."""
    return {"status": "stub", "message": "Sprint 2"}
