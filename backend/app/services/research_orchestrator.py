"""
Research Orchestrator — Phase 6
The 3-Call LLM Pipeline that turns enriched data into a personalized email draft.

Call 1 — Individual Analysis:
  Input:  Individual (DISC, Serper signals, LinkedIn)
  Output: {key_hook, tone_instruction, motivation_trigger, avoid}
  Cache:  30 days on Individual.individual_analysis_cache

Call 2 — Company Analysis:
  Input:  Company (Serper news, OC data, description, sector)
  Output: {mission_fit, news_hook, collaboration_angle, credibility_signal}
  Cache:  7 days on Company.company_analysis_cache

Call 3 — Email Drafter:
  Input:  Individual + Company analysis outputs + sender profile
  Output: Subject + Body (raw email draft)
  No cache — always freshly drafted from latest analysis.

The orchestrator also writes OutreachEmail records to the DB.
"""

import re
import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database.models import (
    Company, Individual, OutreachEmail, OutreachCampaign,
    EmailStatus, TargetType, DISCType,
)
from app.services import llm_service, humantic_service
from app.utils.cache_manager import is_cache_fresh

# TTLs (seconds)
_INDIVIDUAL_ANALYSIS_TTL = settings.INDIVIDUAL_ANALYSIS_CACHE_TTL_SECONDS
_COMPANY_ANALYSIS_TTL = settings.COMPANY_ANALYSIS_CACHE_TTL_SECONDS


# ════════════════════════════════════════════════════════════
#  Call 1 — Individual Analysis
# ════════════════════════════════════════════════════════════

async def run_individual_analysis(
    individual: Individual,
    db: AsyncSession,
    force_refresh: bool = False,
) -> dict:
    """
    LLM Call 1: Analyze an individual's personality and public signals
    to produce tone instructions and a key hook for the email.

    Caches result for 30 days on Individual.individual_analysis_cache.
    Falls back to Humantic DISC data if no Serper signals available.
    """
    # ── Check cache ───────────────────────────────────────────
    if not force_refresh and is_cache_fresh(individual.individual_analysis_cached_at, _INDIVIDUAL_ANALYSIS_TTL):
        return {
            "status": "cached",
            "individual_id": individual.id,
            "data": individual.individual_analysis_cache,
        }

    # ── Build context for prompt ──────────────────────────────
    disc_type = (individual.humantic_disc or DISCType.UNKNOWN).value

    # Use cached Humantic communication pref or get fallback
    fallback = humantic_service.get_fallback_personality(individual)
    comm_pref = individual.humantic_communication_pref or fallback["communication_pref"]

    # Extract Serper signals
    serper_signals = "Not available"
    if individual.serper_individual_cache:
        serper_signals = individual.serper_individual_cache.get("signals", "Not available")

    # Build context object for Jinja2 template
    individual_ctx = {
        "name": individual.name,
        "role": individual.role or "Professional",
        "company": individual.company.name if individual.company else "Unknown Company",
        "linkedin_signals": individual.linkedin_url or "Not available",
        "disc_type": disc_type,
        "communication_pref": comm_pref,
        "serper_mentions": serper_signals[:1000] if serper_signals else "Not available",
    }

    # ── Render prompt ─────────────────────────────────────────
    prompt = llm_service.render_prompt("individual_analysis.j2", individual=individual_ctx)

    # ── Call LLM ──────────────────────────────────────────────
    result = await llm_service.call_llm_json(
        prompt=prompt,
        temperature=0.2,
        max_tokens=600,
        required_keys=["key_hook", "tone_instruction", "motivation_trigger", "avoid"],
    )

    if result["status"] not in ("ok", "missing_keys") or not result.get("data"):
        return {
            "status": result["status"],
            "individual_id": individual.id,
            "error": result.get("error"),
            "data": _fallback_individual_analysis(individual),
        }

    # ── Cache result ──────────────────────────────────────────
    now = datetime.now(timezone.utc)
    individual.individual_analysis_cache = result["data"]
    individual.individual_analysis_cached_at = now
    await db.flush()

    return {
        "status": "ok",
        "individual_id": individual.id,
        "data": result["data"],
        "model": result.get("model"),
        "usage": result.get("usage"),
    }


def _fallback_individual_analysis(individual: Individual) -> dict:
    """Return a generic individual analysis when LLM is unavailable."""
    disc = individual.humantic_disc or DISCType.UNKNOWN
    fallback = humantic_service.get_disc_instructions(disc)
    return {
        "key_hook": f"No specific hook identified for {individual.name}.",
        "tone_instruction": fallback["tone_instruction"],
        "motivation_trigger": f"Professional success in their role as {individual.role or 'their field'}.",
        "avoid": fallback["avoid"],
    }


# ════════════════════════════════════════════════════════════
#  Call 2 — Company Analysis
# ════════════════════════════════════════════════════════════

async def run_company_analysis(
    company: Company,
    db: AsyncSession,
    force_refresh: bool = False,
) -> dict:
    """
    LLM Call 2: Analyze a company's news, mission, and sector
    to produce a news hook, mission fit, and collaboration angle.

    Caches result for 7 days on Company.company_analysis_cache.
    """
    # ── Check cache ───────────────────────────────────────────
    if not force_refresh and is_cache_fresh(company.company_analysis_cached_at, _COMPANY_ANALYSIS_TTL):
        return {
            "status": "cached",
            "company_id": company.id,
            "data": company.company_analysis_cache,
        }

    # ── Extract recent news from Serper cache ─────────────────
    recent_news = []
    if company.serper_news_cache:
        articles = company.serper_news_cache.get("articles", [])
        recent_news = [
            f"{a.get('title', '')} ({a.get('source', '')}, {a.get('date', '')})"
            for a in articles[:5]
            if a.get("title")
        ]

    web_intelligence = "Not available"
    if company.serper_web_cache:
        web_intelligence = company.serper_web_cache.get("intelligence", "Not available")

    # ── Build context for prompt ──────────────────────────────
    company_ctx = {
        "name": company.name,
        "legal_name": company.name,
        "company_type": company.company_type or "Company",
        "jurisdiction_code": company.jurisdiction_code or "Unknown",
        "sector": company.sector or "Unknown",
        "product_type": company.product_type or "Unknown",
        "description": company.description or "Not available",
        "recent_news": recent_news,
        "web_intelligence": web_intelligence[:1500] if web_intelligence else "Not available",
        "company_status": company.company_status or "Active",
        "incorporation_date": (
            company.incorporation_date.strftime("%Y-%m-%d")
            if company.incorporation_date else "Unknown"
        ),
    }

    # ── Render prompt ─────────────────────────────────────────
    prompt = llm_service.render_prompt(
        "company_analysis.j2",
        company=company_ctx,
        nonprofit_mission=settings.NONPROFIT_MISSION,
    )

    # ── Call LLM ──────────────────────────────────────────────
    result = await llm_service.call_llm_json(
        prompt=prompt,
        temperature=0.2,
        max_tokens=600,
        required_keys=["mission_fit", "news_hook", "collaboration_angle", "credibility_signal"],
    )

    if result["status"] not in ("ok", "missing_keys") or not result.get("data"):
        return {
            "status": result["status"],
            "company_id": company.id,
            "error": result.get("error"),
            "data": _fallback_company_analysis(company, recent_news),
        }

    # ── Cache result ──────────────────────────────────────────
    now = datetime.now(timezone.utc)
    company.company_analysis_cache = result["data"]
    company.company_analysis_cached_at = now
    await db.flush()

    return {
        "status": "ok",
        "company_id": company.id,
        "data": result["data"],
        "model": result.get("model"),
        "usage": result.get("usage"),
    }


def _fallback_company_analysis(company: Company, recent_news: list) -> dict:
    """Return a generic company analysis when LLM is unavailable."""
    news_hook = recent_news[0] if recent_news else "No recent news hook available"
    return {
        "mission_fit": f"{company.name} operates in the {company.sector or 'food'} sector, which aligns with our animal advocacy mission.",
        "news_hook": news_hook,
        "collaboration_angle": "Partnership on animal welfare standards and supply chain transparency.",
        "credibility_signal": f"{company.name} has demonstrated commitment through their product focus on {company.product_type or 'sustainable alternatives'}.",
    }


# ════════════════════════════════════════════════════════════
#  Call 3 — Email Drafter
# ════════════════════════════════════════════════════════════

async def run_email_draft(
    individual: Individual,
    company: Company,
    individual_analysis: dict,
    company_analysis: dict,
    previous_contact: Optional[dict] = None,
) -> dict:
    """
    LLM Call 3: Draft the final personalized outreach email.
    Uses outputs from Call 1 + Call 2 as structured inputs.

    No cache — always generates a fresh draft.

    Returns: {status, subject, body, raw, model, usage}
    """
    target_ctx = {
        "name": individual.name,
        "role": individual.role or "Professional",
        "company": company.name,
    }

    # ── Render prompt ─────────────────────────────────────────
    prompt = llm_service.render_prompt(
        "cold_outreach.j2",
        target=target_ctx,
        nonprofit_name=settings.NONPROFIT_NAME,
        nonprofit_mission=settings.NONPROFIT_MISSION,
        sender_name=settings.NONPROFIT_SENDER_NAME,
        sender_role=settings.NONPROFIT_SENDER_ROLE,
        individual_analysis=individual_analysis,
        company_analysis=company_analysis,
        previous_contact=previous_contact,
    )

    # ── Call LLM (higher temperature for more natural writing) ─
    result = await llm_service.call_llm(
        prompt=prompt,
        temperature=0.5,
        max_tokens=800,
    )

    if result["status"] != "ok":
        return {
            "status": result["status"],
            "subject": None,
            "body": None,
            "raw": None,
            "error": result.get("error"),
        }

    # ── Parse Subject / Body from response ───────────────────
    subject, body = _parse_email_output(result["content"])

    return {
        "status": "ok",
        "subject": subject,
        "body": body,
        "raw": result["content"],
        "model": result["model"],
        "usage": result["usage"],
    }


def _parse_email_output(raw: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse the LLM email output into (subject, body).
    Expected format:
      Subject: [subject line here]
      Body:
      [full email body here]
    """
    subject = None
    body = None

    # Extract subject
    subject_match = re.search(r"^Subject:\s*(.+)$", raw, re.MULTILINE | re.IGNORECASE)
    if subject_match:
        subject = subject_match.group(1).strip()

    # Extract body — everything after "Body:" line
    body_match = re.search(r"^Body:\s*\n([\s\S]+)", raw, re.MULTILINE | re.IGNORECASE)
    if body_match:
        body = body_match.group(1).strip()
    elif subject:
        # Fallback: body is everything after the subject line
        parts = raw.split("\n", 2)
        if len(parts) >= 2:
            body = "\n".join(parts[1:]).strip()
            # Remove "Body:" prefix if present
            if body.lower().startswith("body:"):
                body = body[5:].strip()

    return subject, body


# ════════════════════════════════════════════════════════════
#  Full Orchestration Pipeline
# ════════════════════════════════════════════════════════════

async def generate_email_for_target(
    individual: Individual,
    company: Company,
    campaign_id: str,
    db: AsyncSession,
    force_refresh_analysis: bool = False,
    previous_contact: Optional[dict] = None,
) -> dict:
    """
    Run the full 3-call pipeline for one individual target and save the draft.

    Returns:
        {
            status, email_id, subject, body,
            individual_analysis, company_analysis,
            total_tokens, model_used
        }
    """
    # ── Call 1: Individual Analysis ───────────────────────────
    ind_result = await run_individual_analysis(individual, db, force_refresh=force_refresh_analysis)
    individual_analysis = ind_result.get("data") or _fallback_individual_analysis(individual)

    # ── Call 2: Company Analysis ──────────────────────────────
    comp_result = await run_company_analysis(company, db, force_refresh=force_refresh_analysis)
    company_analysis = comp_result.get("data") or _fallback_company_analysis(company, [])

    # ── Call 3: Email Draft ───────────────────────────────────
    draft_result = await run_email_draft(
        individual=individual,
        company=company,
        individual_analysis=individual_analysis,
        company_analysis=company_analysis,
        previous_contact=previous_contact,
    )

    if draft_result["status"] != "ok":
        return {
            "status": draft_result["status"],
            "error": draft_result.get("error"),
            "individual_id": individual.id,
            "company_id": company.id,
        }

    # ── Save OutreachEmail to DB ──────────────────────────────
    email = OutreachEmail(
        campaign_id=campaign_id,
        target_type=TargetType.INDIVIDUAL,
        target_id=individual.id,
        recipient_email=individual.email,
        recipient_name=individual.name,
        company_name=company.name,
        subject=draft_result["subject"],
        body=draft_result["body"],
        status=EmailStatus.DRAFTED,
        drafted_at=datetime.now(timezone.utc),
        llm_model_used=draft_result.get("model"),
        individual_analysis_snapshot=individual_analysis,
        company_analysis_snapshot=company_analysis,
    )
    db.add(email)
    await db.flush()

    # Accumulate token usage across all 3 calls
    total_tokens = sum([
        (ind_result.get("usage") or {}).get("total_tokens", 0),
        (comp_result.get("usage") or {}).get("total_tokens", 0),
        (draft_result.get("usage") or {}).get("total_tokens", 0),
    ])

    return {
        "status": "ok",
        "email_id": email.id,
        "individual_id": individual.id,
        "company_id": company.id,
        "recipient_name": individual.name,
        "recipient_email": individual.email,
        "company_name": company.name,
        "subject": draft_result["subject"],
        "body": draft_result["body"],
        "individual_analysis": individual_analysis,
        "company_analysis": company_analysis,
        "total_tokens": total_tokens,
        "model_used": draft_result.get("model"),
        "call_statuses": {
            "individual_analysis": ind_result["status"],
            "company_analysis": comp_result["status"],
            "email_draft": draft_result["status"],
        },
    }


async def batch_generate_emails(
    target_pairs: list[dict],  # [{individual_id, company_id}]
    campaign_id: str,
    db: AsyncSession,
    concurrency: int = None,
    force_refresh_analysis: bool = False,
) -> list[dict]:
    """
    Generate emails for multiple targets concurrently.

    Args:
        target_pairs: List of {individual_id, company_id} dicts.
        campaign_id: The campaign to associate emails with.
        concurrency: Max simultaneous LLM calls (default: settings.LLM_BATCH_CONCURRENCY).

    Returns: List of per-target generation results.
    """
    max_concurrent = concurrency or settings.LLM_BATCH_CONCURRENCY
    semaphore = asyncio.Semaphore(max_concurrent)

    # Pre-load all individuals and companies
    individual_ids = [p["individual_id"] for p in target_pairs]
    company_ids = list(set(p["company_id"] for p in target_pairs))

    ind_result = await db.execute(
        select(Individual).where(Individual.id.in_(individual_ids))
    )
    comp_result = await db.execute(
        select(Company).where(Company.id.in_(company_ids))
    )

    individuals = {i.id: i for i in ind_result.scalars().all()}
    companies = {c.id: c for c in comp_result.scalars().all()}

    async def _generate_one(pair: dict) -> dict:
        ind_id = pair["individual_id"]
        comp_id = pair["company_id"]
        individual = individuals.get(ind_id)
        company = companies.get(comp_id)

        if not individual:
            return {"status": "error", "individual_id": ind_id, "error": "Individual not found"}
        if not company:
            return {"status": "error", "company_id": comp_id, "error": "Company not found"}

        # Attach company relationship for context
        individual.company = company

        async with semaphore:
            result = await generate_email_for_target(
                individual=individual,
                company=company,
                campaign_id=campaign_id,
                db=db,
                force_refresh_analysis=force_refresh_analysis,
            )
            return result

    results = await asyncio.gather(*[_generate_one(pair) for pair in target_pairs])

    # Commit all drafted emails at once
    await db.commit()

    return list(results)
