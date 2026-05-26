"""
Serper Service — Phase 4
Real-time web and news search using the Serper API (Google search results).

Provides:
  - Company news search  → recent articles, events, launches (for email news_hook)
  - Company web search   → background intelligence, mission, reputation signals
  - Individual search    → public mentions, talks, articles, LinkedIn signals

All results cached with 7-day TTL on Company and Individual models.

Serper API docs: https://serper.dev/api
Free tier: 2,500 requests. Set SERPER_API_KEY in .env.
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

# Serper: 10 concurrent max, 5 requests/second on paid plan
_serper_limiter = RateLimiter(concurrency=5, calls_per_second=3.0)

# 7-day TTL
_TTL = settings.SERPER_CACHE_TTL_SECONDS

_SERPER_HEADERS = {
    "X-API-KEY": settings.SERPER_API_KEY,
    "Content-Type": "application/json",
}


def _get_headers() -> dict:
    """Build headers — re-read key at call time so .env reloads work."""
    return {
        "X-API-KEY": settings.SERPER_API_KEY,
        "Content-Type": "application/json",
    }


# ════════════════════════════════════════════════════════════
#  Core Search Functions
# ════════════════════════════════════════════════════════════

async def news_search(query: str, num: int = 5) -> dict:
    """
    Search Google News via Serper for recent articles about a query.

    Returns:
        {status, query, articles: [{title, link, snippet, source, date, imageUrl}]}
    """
    if not settings.SERPER_API_KEY:
        return {"status": "no_api_key", "articles": []}

    url = f"{settings.SERPER_BASE_URL}/news"
    payload = {"q": query, "num": num, "gl": "us", "hl": "en"}

    async with _serper_limiter:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(url, json=payload, headers=_get_headers())
                resp.raise_for_status()
                data = resp.json()
                articles = data.get("news", [])
                return {
                    "status": "ok",
                    "query": query,
                    "articles": [
                        {
                            "title": a.get("title"),
                            "link": a.get("link"),
                            "snippet": a.get("snippet"),
                            "source": a.get("source"),
                            "date": a.get("date"),
                            "image_url": a.get("imageUrl"),
                        }
                        for a in articles
                    ],
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            except httpx.HTTPStatusError as e:
                return {
                    "status": "error",
                    "error": f"Serper news {e.response.status_code}: {e.response.text[:200]}",
                }
            except httpx.RequestError as e:
                return {"status": "error", "error": str(e)}


async def web_search(query: str, num: int = 5) -> dict:
    """
    Search the web via Serper for background intelligence on a query.

    Returns:
        {status, query, organic: [{title, link, snippet, position}],
         knowledge_graph: {...}, answer_box: {...}}
    """
    if not settings.SERPER_API_KEY:
        return {"status": "no_api_key", "organic": []}

    url = f"{settings.SERPER_BASE_URL}/search"
    payload = {"q": query, "num": num, "gl": "us", "hl": "en"}

    async with _serper_limiter:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(url, json=payload, headers=_get_headers())
                resp.raise_for_status()
                data = resp.json()
                return {
                    "status": "ok",
                    "query": query,
                    "organic": [
                        {
                            "title": r.get("title"),
                            "link": r.get("link"),
                            "snippet": r.get("snippet"),
                            "position": r.get("position"),
                        }
                        for r in data.get("organic", [])
                    ],
                    "knowledge_graph": data.get("knowledgeGraph"),
                    "answer_box": data.get("answerBox"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            except httpx.HTTPStatusError as e:
                return {
                    "status": "error",
                    "error": f"Serper web {e.response.status_code}: {e.response.text[:200]}",
                }
            except httpx.RequestError as e:
                return {"status": "error", "error": str(e)}


# ════════════════════════════════════════════════════════════
#  Company Enrichment
# ════════════════════════════════════════════════════════════

def _build_company_queries(company: Company) -> dict[str, str]:
    """Build targeted search queries for a company."""
    name = company.name
    queries = {
        "news": f'"{name}" news',
        "web": f'"{name}" {company.industry or "company"} sustainability animal welfare',
    }
    if company.product_type:
        queries["news"] = f'"{name}" {company.product_type} news'
    return queries


def _extract_company_intelligence(web_result: dict, news_result: dict) -> str:
    """
    Synthesize a plain-text intelligence summary from Serper results.
    This is fed into LLM Call 2 (Company Analysis).
    """
    lines = []

    # Knowledge graph
    kg = web_result.get("knowledge_graph")
    if kg:
        desc = kg.get("description") or kg.get("descriptionSource")
        if desc:
            lines.append(f"About: {desc}")
        founded = kg.get("founded")
        if founded:
            lines.append(f"Founded: {founded}")
        hq = kg.get("headquarters")
        if hq:
            lines.append(f"HQ: {hq}")

    # Answer box
    ab = web_result.get("answer_box")
    if ab and ab.get("snippet"):
        lines.append(f"Highlight: {ab['snippet']}")

    # Top organic results
    for r in (web_result.get("organic") or [])[:3]:
        snippet = r.get("snippet", "")
        if snippet:
            lines.append(f"Web: {snippet}")

    # Recent news
    for a in (news_result.get("articles") or [])[:3]:
        title = a.get("title", "")
        date = a.get("date", "")
        source = a.get("source", "")
        if title:
            lines.append(f"News ({date}, {source}): {title}")

    return "\n".join(lines) if lines else "No intelligence gathered."


def _get_recent_news_hook(news_result: dict) -> Optional[str]:
    """Extract the single strongest, most recent news item as a hook string."""
    articles = news_result.get("articles") or []
    if not articles:
        return None
    # First article is most recent (Serper sorts by date)
    a = articles[0]
    title = a.get("title", "")
    source = a.get("source", "")
    date = a.get("date", "")
    if title:
        parts = [title]
        if source:
            parts.append(f"({source}")
        if date:
            parts.append(f"— {date})")
        else:
            if source:
                parts[-1] += ")"
        return " ".join(parts)
    return None


async def enrich_company(
    company: Company,
    db: AsyncSession,
    force_refresh: bool = False,
) -> dict:
    """
    Run Serper news + web search for a company and cache results.
    Respects 7-day TTL.

    Updates:
      - company.serper_news_cache
      - company.serper_web_cache
      - company.serper_cached_at
    """
    # ── Check cache ───────────────────────────────────────────
    if not force_refresh and is_cache_fresh(company.serper_cached_at, _TTL):
        return {
            "status": "cached",
            "company_id": company.id,
            "company_name": company.name,
            "cached_at": company.serper_cached_at.isoformat(),
            "news_hook": _get_recent_news_hook(company.serper_news_cache or {}),
            "intelligence_snippet": (company.serper_web_cache or {}).get("intelligence"),
        }

    # ── Run searches ──────────────────────────────────────────
    queries = _build_company_queries(company)

    news_result = await news_search(queries["news"], num=5)
    web_result = await web_search(queries["web"], num=5)

    # ── Process + store ───────────────────────────────────────
    now = datetime.now(timezone.utc)
    intelligence = _extract_company_intelligence(web_result, news_result)
    news_hook = _get_recent_news_hook(news_result)

    # Attach intelligence summary to cache for easy LLM consumption
    web_result["intelligence"] = intelligence

    company.serper_news_cache = news_result
    company.serper_web_cache = web_result
    company.serper_cached_at = now

    await db.flush()

    return {
        "status": news_result.get("status") or web_result.get("status") or "ok",
        "company_id": company.id,
        "company_name": company.name,
        "news_query": queries["news"],
        "web_query": queries["web"],
        "news_articles_found": len(news_result.get("articles", [])),
        "web_results_found": len(web_result.get("organic", [])),
        "news_hook": news_hook,
        "intelligence_snippet": intelligence[:300] + "..." if len(intelligence) > 300 else intelligence,
    }


# ════════════════════════════════════════════════════════════
#  Individual Enrichment
# ════════════════════════════════════════════════════════════

def _build_individual_queries(individual: Individual) -> dict[str, str]:
    """Build targeted search queries for an individual."""
    name = individual.name
    company = individual.company.name if individual.company else ""
    role = individual.role or ""

    queries = {
        "mentions": (
            f'"{name}" {company} {role}'
            if company else f'"{name}" {role}'
        ).strip(),
        "talks": f'"{name}" talk OR interview OR conference OR podcast animal welfare',
        "linkedin": f'"{name}" {company} LinkedIn site:linkedin.com',
    }
    return queries


def _extract_individual_signals(results: dict) -> str:
    """
    Synthesize plain-text public signals for an individual.
    Fed into LLM Call 1 (Individual Analysis).
    """
    lines = []

    mentions = results.get("mentions", {}).get("organic") or []
    for r in mentions[:3]:
        snippet = r.get("snippet", "")
        title = r.get("title", "")
        if snippet or title:
            lines.append(f"Mention: {title} — {snippet}")

    talks = results.get("talks", {}).get("organic") or []
    for r in talks[:2]:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        if title:
            lines.append(f"Public appearance: {title}")
            if snippet:
                lines.append(f"  Detail: {snippet}")

    news = results.get("mentions", {}).get("articles") or []
    for a in news[:2]:
        title = a.get("title", "")
        if title:
            lines.append(f"News mention: {title}")

    return "\n".join(lines) if lines else "No public signals found."


async def enrich_individual(
    individual: Individual,
    db: AsyncSession,
    force_refresh: bool = False,
) -> dict:
    """
    Run Serper search for an individual's public presence and cache results.
    Respects 7-day TTL.

    Updates:
      - individual.serper_individual_cache
      - individual.serper_cached_at
    """
    # ── Check cache ───────────────────────────────────────────
    if not force_refresh and is_cache_fresh(individual.serper_cached_at, _TTL):
        cached = individual.serper_individual_cache or {}
        return {
            "status": "cached",
            "individual_id": individual.id,
            "name": individual.name,
            "cached_at": individual.serper_cached_at.isoformat(),
            "signals_snippet": cached.get("signals", "")[:300],
        }

    # ── Load company relationship if not already loaded ───────
    if individual.company_id and not individual.company:
        from sqlalchemy import select as sel
        comp_result = await db.execute(
            sel(Company).where(Company.id == individual.company_id)
        )
        individual.company = comp_result.scalar_one_or_none()

    # ── Run searches ──────────────────────────────────────────
    queries = _build_individual_queries(individual)

    mentions_result = await web_search(queries["mentions"], num=5)
    talks_result = await web_search(queries["talks"], num=3)

    # ── Process + store ───────────────────────────────────────
    now = datetime.now(timezone.utc)
    signals = _extract_individual_signals({
        "mentions": mentions_result,
        "talks": talks_result,
    })

    cache_data = {
        "mentions": mentions_result,
        "talks": talks_result,
        "signals": signals,
        "queries": queries,
        "fetched_at": now.isoformat(),
    }

    individual.serper_individual_cache = cache_data
    individual.serper_cached_at = now

    await db.flush()

    return {
        "status": "ok",
        "individual_id": individual.id,
        "name": individual.name,
        "mention_results": len(mentions_result.get("organic", [])),
        "talk_results": len(talks_result.get("organic", [])),
        "signals_snippet": signals[:300] + "..." if len(signals) > 300 else signals,
    }


# ════════════════════════════════════════════════════════════
#  Batch Enrichment
# ════════════════════════════════════════════════════════════

async def batch_enrich_companies(
    company_ids: list[str],
    db: AsyncSession,
    force_refresh: bool = False,
) -> list[dict]:
    """Enrich multiple companies from Serper. Max 50 per call."""
    import asyncio

    stmt = select(Company).where(Company.id.in_(company_ids))
    result = await db.execute(stmt)
    companies = result.scalars().all()

    results = []
    for company in companies:
        r = await enrich_company(company, db, force_refresh=force_refresh)
        results.append(r)
        await asyncio.sleep(0.2)  # polite delay

    await db.commit()
    return results


async def batch_enrich_individuals(
    individual_ids: list[str],
    db: AsyncSession,
    force_refresh: bool = False,
) -> list[dict]:
    """Enrich multiple individuals from Serper."""
    import asyncio

    stmt = select(Individual).where(Individual.id.in_(individual_ids))
    result = await db.execute(stmt)
    individuals = result.scalars().all()

    results = []
    for ind in individuals:
        r = await enrich_individual(ind, db, force_refresh=force_refresh)
        results.append(r)
        await asyncio.sleep(0.2)

    await db.commit()
    return results
