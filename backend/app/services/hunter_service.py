"""
Hunter.io Service — Phase 3
Discovers verified email addresses for company contacts.

Provides:
  - Domain search: find all email addresses for a company domain
  - Email finder: find a specific person's email by name + domain
  - Email verifier: verify an existing email address
  - 14-day TTL caching on Company + Individual models

Hunter.io API docs: https://hunter.io/api-documentation
Free tier: 25 searches/month. Paid plans for production use.
"""

import httpx
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database.models import Company, Individual
from app.utils.cache_manager import is_cache_fresh
from app.utils.rate_limiter import RateLimiter

# Hunter.io free tier: conservative rate limiting
_hunter_limiter = RateLimiter(concurrency=3, calls_per_second=1.0)

# 14-day TTL
_TTL = settings.HUNTER_CACHE_TTL_SECONDS


def _build_params(extra: dict = None) -> dict:
    params = {"api_key": settings.HUNTER_API_KEY}
    if extra:
        params.update(extra)
    return params


def _extract_domain_from_website(website: Optional[str]) -> Optional[str]:
    """Extract bare domain from a URL string. e.g. https://www.beyondmeat.com → beyondmeat.com"""
    if not website:
        return None
    domain = website.strip().lower()
    for prefix in ("https://", "http://", "www."):
        domain = domain.removeprefix(prefix)
    domain = domain.split("/")[0].split("?")[0]
    return domain or None


# ════════════════════════════════════════════════════════════
#  Domain Search — find all contacts for a company
# ════════════════════════════════════════════════════════════

async def domain_search(
    domain: str,
    department: Optional[str] = None,  # e.g. "management", "sales", "marketing"
    limit: int = 10,
) -> dict:
    """
    Search all email addresses associated with a domain on Hunter.io.

    Returns a structured dict with:
      - emails: list of {email, first_name, last_name, position, confidence, linkedin}
      - organization: company metadata from Hunter
      - total: total emails found for this domain
    """
    if not settings.HUNTER_API_KEY:
        return {"status": "no_api_key", "emails": [], "total": 0}

    params = _build_params({
        "domain": domain,
        "limit": limit,
    })
    if department:
        params["department"] = department

    url = f"{settings.HUNTER_BASE_URL}/domain-search"

    async with _hunter_limiter:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json().get("data", {})
                emails = data.get("emails", [])

                return {
                    "status": "ok",
                    "domain": domain,
                    "total": data.get("total", len(emails)),
                    "organization": data.get("organization"),
                    "emails": [
                        {
                            "email": e.get("value"),
                            "first_name": e.get("first_name"),
                            "last_name": e.get("last_name"),
                            "position": e.get("position"),
                            "seniority": e.get("seniority"),
                            "department": e.get("department"),
                            "confidence": e.get("confidence", 0),
                            "linkedin": e.get("linkedin"),
                            "verified": e.get("verification", {}).get("status") == "valid",
                            "sources": [s.get("uri") for s in e.get("sources", [])],
                        }
                        for e in emails
                    ],
                }
            except httpx.HTTPStatusError as e:
                return {"status": "error", "error": f"Hunter {e.response.status_code}: {e.response.text[:200]}"}
            except httpx.RequestError as e:
                return {"status": "error", "error": str(e)}


# ════════════════════════════════════════════════════════════
#  Email Finder — find one specific person's email
# ════════════════════════════════════════════════════════════

async def find_email(
    domain: str,
    first_name: str,
    last_name: str,
) -> dict:
    """
    Find a specific person's email address from their name + company domain.

    Returns:
      {status, email, confidence, score, verified}
    """
    if not settings.HUNTER_API_KEY:
        return {"status": "no_api_key"}

    url = f"{settings.HUNTER_BASE_URL}/email-finder"
    params = _build_params({
        "domain": domain,
        "first_name": first_name,
        "last_name": last_name,
    })

    async with _hunter_limiter:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return {
                    "status": "ok",
                    "email": data.get("email"),
                    "confidence": data.get("confidence", 0),
                    "score": data.get("score", 0),
                    "first_name": data.get("first_name"),
                    "last_name": data.get("last_name"),
                    "position": data.get("position"),
                    "linkedin": data.get("linkedin"),
                    "verified": data.get("verification", {}).get("status") == "valid",
                }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return {"status": "not_found"}
                return {"status": "error", "error": f"Hunter {e.response.status_code}: {e.response.text[:200]}"}
            except httpx.RequestError as e:
                return {"status": "error", "error": str(e)}


# ════════════════════════════════════════════════════════════
#  Email Verifier
# ════════════════════════════════════════════════════════════

async def verify_email(email: str) -> dict:
    """
    Verify whether an email address is valid using Hunter.io verifier.

    Returns:
      {status, result: "valid"|"invalid"|"unknown", score, regexp, gibberish, disposable, webmail, mx_records}
    """
    if not settings.HUNTER_API_KEY:
        return {"status": "no_api_key"}

    url = f"{settings.HUNTER_BASE_URL}/email-verifier"
    params = _build_params({"email": email})

    async with _hunter_limiter:
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return {
                    "status": "ok",
                    "email": data.get("email"),
                    "result": data.get("result"),          # "valid", "invalid", "unknown"
                    "score": data.get("score", 0),
                    "regexp": data.get("regexp"),
                    "gibberish": data.get("gibberish"),
                    "disposable": data.get("disposable"),
                    "webmail": data.get("webmail"),
                    "mx_records": data.get("mx_records"),
                }
            except httpx.HTTPStatusError as e:
                return {"status": "error", "error": f"Hunter {e.response.status_code}: {e.response.text[:200]}"}
            except httpx.RequestError as e:
                return {"status": "error", "error": str(e)}


# ════════════════════════════════════════════════════════════
#  Company Enrichment (domain search + cache)
# ════════════════════════════════════════════════════════════

async def enrich_company_contacts(
    company: Company,
    db: AsyncSession,
    force_refresh: bool = False,
    limit: int = 10,
) -> dict:
    """
    Run Hunter.io domain search for a company and cache the results.
    Respects 14-day TTL.
    """
    # ── Check cache ───────────────────────────────────────────
    if not force_refresh and is_cache_fresh(company.hunter_cached_at, _TTL):
        return {
            "status": "cached",
            "company_id": company.id,
            "company_name": company.name,
            "cached_at": company.hunter_cached_at.isoformat(),
            "data": company.hunter_domain_cache,
        }

    # ── Extract domain ────────────────────────────────────────
    domain = _extract_domain_from_website(company.website)
    if not domain:
        return {
            "status": "no_domain",
            "company_id": company.id,
            "company_name": company.name,
            "message": "Company has no website set — cannot run Hunter domain search.",
        }

    # ── Call Hunter ───────────────────────────────────────────
    result = await domain_search(domain, limit=limit)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    company.hunter_domain_cache = result
    company.hunter_cached_at = now

    # If Hunter returned a company email, use it
    if result.get("status") == "ok":
        org = result.get("organization")
        if org and not company.email:
            # Hunter sometimes returns a generic contact email for the domain
            emails = result.get("emails", [])
            if emails:
                best_email = max(emails, key=lambda e: e.get("confidence", 0))
                company.email = best_email.get("email")

    await db.flush()
    return {"status": result.get("status"), "company_id": company.id, **result}


# ════════════════════════════════════════════════════════════
#  Individual Enrichment (email finder + verify + cache)
# ════════════════════════════════════════════════════════════

async def enrich_individual_email(
    individual: Individual,
    db: AsyncSession,
    force_refresh: bool = False,
) -> dict:
    """
    Find and verify an individual's email address via Hunter.io.
    Respects 14-day TTL cache.
    """
    # ── Check cache ───────────────────────────────────────────
    if not force_refresh and individual.email and individual.email_verified:
        return {
            "status": "already_verified",
            "individual_id": individual.id,
            "email": individual.email,
            "confidence": individual.email_confidence,
        }

    # ── Need domain — get from company ────────────────────────
    domain = None
    if individual.company:
        domain = _extract_domain_from_website(individual.company.website)

    if not domain:
        return {
            "status": "no_domain",
            "individual_id": individual.id,
            "name": individual.name,
            "message": "No company domain available to search Hunter.",
        }

    if not individual.first_name or not individual.last_name:
        return {
            "status": "no_name",
            "individual_id": individual.id,
            "message": "first_name and last_name required for Hunter email finder.",
        }

    # ── Find email ────────────────────────────────────────────
    result = await find_email(
        domain=domain,
        first_name=individual.first_name,
        last_name=individual.last_name,
    )

    if result.get("status") == "ok" and result.get("email"):
        individual.email = result["email"]
        individual.email_confidence = result.get("confidence", 0)
        individual.email_verified = result.get("verified", False)

        # Fill in role if we found it and it's currently empty
        if result.get("position") and not individual.role:
            individual.role = result["position"]
        if result.get("linkedin") and not individual.linkedin_url:
            individual.linkedin_url = result["linkedin"]

        await db.flush()
        return {
            "status": "found",
            "individual_id": individual.id,
            "email": individual.email,
            "confidence": individual.email_confidence,
            "verified": individual.email_verified,
        }

    return {
        "status": result.get("status", "not_found"),
        "individual_id": individual.id,
        "name": individual.name,
    }
