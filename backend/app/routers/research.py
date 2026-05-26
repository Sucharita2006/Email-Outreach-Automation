"""
Research Router — Phase 3: OpenCorporates + Hunter.io endpoints
Exposes endpoints to trigger and retrieve enrichment for companies and individuals.

Phase 3 endpoints:
  POST /research/company/{id}/opencorporates   — Enrich company from OpenCorporates registry
  POST /research/company/{id}/hunter           — Run Hunter.io domain search for company
  POST /research/individual/{id}/hunter        — Find individual email via Hunter.io
  POST /research/company/{id}/enrich-all       — Run both OpenCorporates + Hunter in one call
  POST /research/batch/opencorporates          — Batch enrich multiple companies
  GET  /research/company/{id}/status           — View current research cache status
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.session import get_db
from app.database.models import Company, Individual
from app.services import opencorporates_service, hunter_service
from app.utils.cache_manager import is_cache_fresh, cache_age_hours
from app.config import settings

router = APIRouter()


# ════════════════════════════════════════════════════════════
#  OpenCorporates Enrichment
# ════════════════════════════════════════════════════════════

@router.post("/company/{company_id}/opencorporates")
async def enrich_company_opencorporates(
    company_id: str,
    force_refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Enrich a company from the OpenCorporates company registry.
    Fills in: jurisdiction_code, company_status, incorporation_date,
              company_type, registered_address, legal name.
    Respects 30-day TTL cache.
    """
    company = await _get_company_or_404(company_id, db)
    result = await opencorporates_service.enrich_company(
        company, db, force_refresh=force_refresh
    )
    await db.commit()
    return result


@router.post("/batch/opencorporates")
async def batch_enrich_opencorporates(
    company_ids: list[str] = Body(..., description="List of company IDs to enrich"),
    force_refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Batch enrich multiple companies from OpenCorporates.
    Processes sequentially with 0.3s delay to respect free tier rate limits.
    Max 50 companies per call.
    """
    if len(company_ids) > 50:
        raise HTTPException(status_code=400, detail="Max 50 companies per batch call.")

    results = await opencorporates_service.batch_enrich_companies(
        company_ids, db, force_refresh=force_refresh
    )
    return {
        "total": len(results),
        "enriched": sum(1 for r in results if r.get("status") == "enriched"),
        "cached": sum(1 for r in results if r.get("status") == "cached"),
        "not_found": sum(1 for r in results if r.get("status") == "not_found"),
        "errors": sum(1 for r in results if r.get("status") == "error"),
        "results": results,
    }


# ════════════════════════════════════════════════════════════
#  Hunter.io Enrichment
# ════════════════════════════════════════════════════════════

@router.post("/company/{company_id}/hunter")
async def enrich_company_hunter(
    company_id: str,
    force_refresh: bool = False,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """
    Run a Hunter.io domain search for a company to discover contacts.
    Caches results for 14 days on the Company record.
    Requires: HUNTER_API_KEY in .env and company.website to be set.
    """
    company = await _get_company_or_404(company_id, db)
    result = await hunter_service.enrich_company_contacts(
        company, db, force_refresh=force_refresh, limit=limit
    )
    await db.commit()
    return result


@router.post("/individual/{individual_id}/hunter")
async def enrich_individual_hunter(
    individual_id: str,
    force_refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Find and verify an individual's email address via Hunter.io email finder.
    Requires: first_name, last_name, and a linked company with a website.
    """
    stmt = select(Individual).where(Individual.id == individual_id)
    result = await db.execute(stmt)
    individual = result.scalar_one_or_none()
    if not individual:
        raise HTTPException(status_code=404, detail="Individual not found")

    # Load related company for domain extraction
    if individual.company_id:
        comp_result = await db.execute(
            select(Company).where(Company.id == individual.company_id)
        )
        individual.company = comp_result.scalar_one_or_none()

    enrichment = await hunter_service.enrich_individual_email(
        individual, db, force_refresh=force_refresh
    )
    await db.commit()
    return enrichment


# ════════════════════════════════════════════════════════════
#  Combined Enrichment (OpenCorporates + Hunter in one call)
# ════════════════════════════════════════════════════════════

@router.post("/company/{company_id}/enrich-all")
async def enrich_company_all(
    company_id: str,
    force_refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Run all Phase 3 enrichment for a single company:
      1. OpenCorporates (registry data)
      2. Hunter.io (email contacts)

    Each step is independently cached and skipped if fresh.
    Returns a combined summary.
    """
    company = await _get_company_or_404(company_id, db)

    oc_result = await opencorporates_service.enrich_company(
        company, db, force_refresh=force_refresh
    )
    hunter_result = await hunter_service.enrich_company_contacts(
        company, db, force_refresh=force_refresh
    )
    await db.commit()

    return {
        "company_id": company_id,
        "company_name": company.name,
        "opencorporates": oc_result,
        "hunter": hunter_result,
    }


# ════════════════════════════════════════════════════════════
#  Research Status / Cache Inspection
# ════════════════════════════════════════════════════════════

@router.get("/company/{company_id}/status")
async def company_research_status(
    company_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Show the current research enrichment status for a company.
    Indicates which caches are fresh, stale, or missing.
    """
    company = await _get_company_or_404(company_id, db)

    oc_ttl = settings.OPENCORPORATES_CACHE_TTL_SECONDS
    hunter_ttl = settings.HUNTER_CACHE_TTL_SECONDS
    serper_ttl = settings.SERPER_CACHE_TTL_SECONDS
    analysis_ttl = settings.COMPANY_ANALYSIS_CACHE_TTL_SECONDS

    return {
        "company_id": company.id,
        "company_name": company.name,
        "website": company.website,
        "enrichment_status": {
            "opencorporates": {
                "fresh": is_cache_fresh(company.opencorporates_cached_at, oc_ttl),
                "cached_hours_ago": cache_age_hours(company.opencorporates_cached_at),
                "ttl_days": oc_ttl // 86400,
                "has_data": bool(company.opencorporates_cache),
                "jurisdiction_code": company.jurisdiction_code,
                "company_status": company.company_status,
                "company_type": company.company_type,
            },
            "hunter": {
                "fresh": is_cache_fresh(company.hunter_cached_at, hunter_ttl),
                "cached_hours_ago": cache_age_hours(company.hunter_cached_at),
                "ttl_days": hunter_ttl // 86400,
                "has_data": bool(company.hunter_domain_cache),
                "email_count": len(
                    (company.hunter_domain_cache or {}).get("emails", [])
                ),
            },
            "serper": {
                "fresh": is_cache_fresh(company.serper_cached_at, serper_ttl),
                "cached_hours_ago": cache_age_hours(company.serper_cached_at),
                "ttl_days": serper_ttl // 86400,
                "has_data": bool(company.serper_news_cache or company.serper_web_cache),
            },
            "company_analysis": {
                "fresh": is_cache_fresh(company.company_analysis_cached_at, analysis_ttl),
                "cached_hours_ago": cache_age_hours(company.company_analysis_cached_at),
                "ttl_days": analysis_ttl // 86400,
                "has_data": bool(company.company_analysis_cache),
            },
        },
    }


@router.get("/individual/{individual_id}/status")
async def individual_research_status(
    individual_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Show the current research cache status for an individual."""
    stmt = select(Individual).where(Individual.id == individual_id)
    result = await db.execute(stmt)
    individual = result.scalar_one_or_none()
    if not individual:
        raise HTTPException(status_code=404, detail="Individual not found")

    humantic_ttl = settings.HUMANTIC_CACHE_TTL_SECONDS
    serper_ttl = settings.SERPER_CACHE_TTL_SECONDS
    analysis_ttl = settings.INDIVIDUAL_ANALYSIS_CACHE_TTL_SECONDS

    return {
        "individual_id": individual.id,
        "name": individual.name,
        "email": individual.email,
        "email_verified": individual.email_verified,
        "email_confidence": individual.email_confidence,
        "enrichment_status": {
            "hunter": {
                "email_found": bool(individual.email),
                "email_verified": bool(individual.email_verified),
                "confidence": individual.email_confidence,
            },
            "humantic": {
                "fresh": is_cache_fresh(individual.humantic_cached_at, humantic_ttl),
                "cached_hours_ago": cache_age_hours(individual.humantic_cached_at),
                "ttl_days": humantic_ttl // 86400,
                "disc_type": individual.humantic_disc,
                "has_data": bool(individual.humantic_disc and individual.humantic_disc != "UNKNOWN"),
            },
            "serper": {
                "fresh": is_cache_fresh(individual.serper_cached_at, serper_ttl),
                "cached_hours_ago": cache_age_hours(individual.serper_cached_at),
                "ttl_days": serper_ttl // 86400,
                "has_data": bool(individual.serper_individual_cache),
            },
            "individual_analysis": {
                "fresh": is_cache_fresh(individual.individual_analysis_cached_at, analysis_ttl),
                "cached_hours_ago": cache_age_hours(individual.individual_analysis_cached_at),
                "ttl_days": analysis_ttl // 86400,
                "has_data": bool(individual.individual_analysis_cache),
            },
        },
    }


# ════════════════════════════════════════════════════════════
#  Stubs for later phases (Serper, Humantic, LLM orchestrator)
# ════════════════════════════════════════════════════════════

@router.post("/company/{company_id}/serper")
async def enrich_company_serper(company_id: str, db: AsyncSession = Depends(get_db)):
    """Serper web + news search enrichment — Phase 4."""
    return {"status": "stub", "message": "Phase 4: Serper integration", "company_id": company_id}


@router.post("/individual/{individual_id}/humantic")
async def enrich_individual_humantic(individual_id: str, db: AsyncSession = Depends(get_db)):
    """Humantic AI personality profiling — Phase 5."""
    return {"status": "stub", "message": "Phase 5: Humantic integration", "individual_id": individual_id}


@router.post("/individual/{individual_id}/serper")
async def enrich_individual_serper(individual_id: str, db: AsyncSession = Depends(get_db)):
    """Serper public mention search for individual — Phase 4."""
    return {"status": "stub", "message": "Phase 4: Serper integration", "individual_id": individual_id}


# ════════════════════════════════════════════════════════════
#  Helper
# ════════════════════════════════════════════════════════════

async def _get_company_or_404(company_id: str, db: AsyncSession) -> Company:
    stmt = select(Company).where(Company.id == company_id)
    result = await db.execute(stmt)
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
