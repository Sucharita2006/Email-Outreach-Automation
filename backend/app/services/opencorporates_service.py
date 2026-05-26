"""
OpenCorporates Service — Phase 3
Looks up company registration data from the OpenCorporates API.

Provides:
  - Company search by name + optional jurisdiction
  - Company detail fetch by opencorporates_id
  - 30-day TTL caching on Company model

OpenCorporates API docs: https://api.opencorporates.com/documentation/API-Reference
Free tier: 500 requests/day (no auth needed for basic search)
Paid token: set OPENCORPORATES_API_TOKEN in .env for higher limits.
"""

import httpx
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database.models import Company
from app.utils.cache_manager import is_cache_fresh
from app.utils.rate_limiter import RateLimiter

# 5 concurrent requests max to OpenCorporates
_oc_limiter = RateLimiter(concurrency=5, calls_per_second=2.0)

# 30-day TTL
_TTL = settings.OPENCORPORATES_CACHE_TTL_SECONDS


def _build_headers() -> dict:
    headers = {"Accept": "application/json", "User-Agent": "EmailOutreachAutomation/0.1"}
    if settings.OPENCORPORATES_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.OPENCORPORATES_API_TOKEN}"
    return headers


def _parse_company_result(oc_company: dict) -> dict:
    """
    Normalize an OpenCorporates company object into our internal schema.
    Handles both search result format and direct company detail format.
    """
    c = oc_company.get("company", oc_company)

    # Parse incorporation date safely
    inc_date = None
    raw_date = c.get("incorporation_date")
    if raw_date:
        try:
            inc_date = datetime.strptime(raw_date, "%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    return {
        "opencorporates_id": c.get("company_number"),
        "jurisdiction_code": c.get("jurisdiction_code"),
        "company_status": c.get("current_status") or c.get("company_status"),
        "incorporation_date": inc_date,
        "company_type": c.get("company_type"),
        "registered_address": _extract_address(c.get("registered_address")),
        "legal_name": c.get("name"),
        "opencorporates_url": c.get("opencorporates_url"),
        "source_data": c,  # Store full response for future reference
    }


def _extract_address(addr: Optional[dict]) -> Optional[str]:
    """Convert OpenCorporates address dict to single string."""
    if not addr:
        return None
    parts = []
    for key in ("street_address", "locality", "region", "postal_code", "country"):
        val = addr.get(key)
        if val:
            parts.append(str(val))
    return ", ".join(parts) if parts else None


async def search_company(
    name: str,
    jurisdiction_code: Optional[str] = None,
    max_results: int = 5,
) -> list[dict]:
    """
    Search OpenCorporates for companies matching the given name.

    Args:
        name: Company name to search for.
        jurisdiction_code: Optional jurisdiction filter e.g. "us_de", "gb", "us_ca".
        max_results: Max number of results to return.

    Returns:
        List of normalized company dicts, ordered by relevance.
    """
    params = {
        "q": name,
        "per_page": max_results,
        "sparse": "true",       # Smaller response payload
    }
    if jurisdiction_code:
        params["jurisdiction_code"] = jurisdiction_code
    if settings.OPENCORPORATES_API_TOKEN:
        params["api_token"] = settings.OPENCORPORATES_API_TOKEN

    url = f"{settings.OPENCORPORATES_BASE_URL}/companies/search"

    async with _oc_limiter:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, params=params, headers=_build_headers())
                resp.raise_for_status()
                data = resp.json()
                companies = (
                    data.get("results", {})
                        .get("companies", [])
                )
                return [_parse_company_result(c) for c in companies]
            except httpx.HTTPStatusError as e:
                raise RuntimeError(
                    f"OpenCorporates search failed ({e.response.status_code}): {e.response.text[:200]}"
                )
            except httpx.RequestError as e:
                raise RuntimeError(f"OpenCorporates request error: {e}")


async def fetch_company_detail(
    company_number: str,
    jurisdiction_code: str,
) -> dict:
    """
    Fetch full company detail from OpenCorporates by company number + jurisdiction.

    Args:
        company_number: The company registration number.
        jurisdiction_code: Jurisdiction e.g. "us_de", "gb".

    Returns:
        Normalized company detail dict.
    """
    url = f"{settings.OPENCORPORATES_BASE_URL}/companies/{jurisdiction_code}/{company_number}"
    params = {}
    if settings.OPENCORPORATES_API_TOKEN:
        params["api_token"] = settings.OPENCORPORATES_API_TOKEN

    async with _oc_limiter:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, params=params, headers=_build_headers())
                resp.raise_for_status()
                data = resp.json()
                return _parse_company_result(data.get("results", {}).get("company", {}))
            except httpx.HTTPStatusError as e:
                raise RuntimeError(
                    f"OpenCorporates detail failed ({e.response.status_code}): {e.response.text[:200]}"
                )
            except httpx.RequestError as e:
                raise RuntimeError(f"OpenCorporates request error: {e}")


async def enrich_company(
    company: Company,
    db: AsyncSession,
    force_refresh: bool = False,
) -> dict:
    """
    Main entry point: enrich a Company record from OpenCorporates.
    Respects 30-day TTL cache — only calls API if cache is stale.

    Returns a summary dict with what was found/updated.
    """
    # ── Check cache ───────────────────────────────────────────
    if not force_refresh and is_cache_fresh(company.opencorporates_cached_at, _TTL):
        return {
            "status": "cached",
            "company_id": company.id,
            "company_name": company.name,
            "cached_at": company.opencorporates_cached_at.isoformat(),
            "data": company.opencorporates_cache,
        }

    # ── Search OpenCorporates ─────────────────────────────────
    try:
        results = await search_company(company.name, max_results=3)
    except RuntimeError as e:
        return {"status": "error", "company_id": company.id, "error": str(e)}

    if not results:
        return {
            "status": "not_found",
            "company_id": company.id,
            "company_name": company.name,
        }

    # Take the best match (first result — OpenCorporates sorts by relevance)
    best = results[0]

    # ── Update Company model ──────────────────────────────────
    now = datetime.now(timezone.utc)

    # Only overwrite fields that are currently empty (don't clobber manual data)
    if not company.opencorporates_id:
        company.opencorporates_id = best["opencorporates_id"]
    if not company.jurisdiction_code:
        company.jurisdiction_code = best["jurisdiction_code"]
    if not company.company_status:
        company.company_status = best["company_status"]
    if not company.incorporation_date:
        company.incorporation_date = best["incorporation_date"]
    if not company.company_type:
        company.company_type = best["company_type"]
    if not company.registered_address:
        company.registered_address = best["registered_address"]

    # Always update the cache
    company.opencorporates_cache = best
    company.opencorporates_cached_at = now

    await db.flush()

    return {
        "status": "enriched",
        "company_id": company.id,
        "company_name": company.name,
        "matched_legal_name": best.get("legal_name"),
        "jurisdiction_code": best.get("jurisdiction_code"),
        "company_status": best.get("company_status"),
        "incorporation_date": best["incorporation_date"].isoformat() if best.get("incorporation_date") else None,
        "company_type": best.get("company_type"),
        "opencorporates_url": best.get("opencorporates_url"),
    }


async def batch_enrich_companies(
    company_ids: list[str],
    db: AsyncSession,
    force_refresh: bool = False,
) -> list[dict]:
    """
    Enrich multiple companies from OpenCorporates in sequence (respects rate limits).
    Returns a list of per-company result dicts.
    """
    import asyncio

    results = []
    stmt = select(Company).where(Company.id.in_(company_ids))
    company_result = await db.execute(stmt)
    companies = company_result.scalars().all()

    for company in companies:
        result = await enrich_company(company, db, force_refresh=force_refresh)
        results.append(result)
        # Small delay between requests to be polite to the free tier
        await asyncio.sleep(0.3)

    await db.commit()
    return results
