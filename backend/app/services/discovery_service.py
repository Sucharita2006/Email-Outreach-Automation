"""
Discovery Service — Domain-Driven Target Discovery

Orchestrates the full discovery pipeline:
  1. DB search  — fuzzy domain tag + sector/description match in existing records
  2. Serper      — live web search for companies not yet in the DB
  3. Hunter      — find decision-maker contacts at each matched company
  4. Save        — upsert new companies/individuals to DB
  5. Background  — fire-and-forget enrichment (Hunter + OC + Serper + Humantic)

Usage (from router):
    results = await discover_targets(domain, campaign_purpose, db)
    background_tasks.add_task(enrich_discovered_targets, new_company_ids, new_individual_ids)
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, cast, String, func

from app.config import settings
from app.database.models import Company, Individual
from app.database.session import AsyncSessionLocal
from app.services import serper_service, hunter_service, opencorporates_service, humantic_service
from app.utils.fuzzy_match import expand_domain_query


# ════════════════════════════════════════════════════════════
#  Layer 1 — DB Search
# ════════════════════════════════════════════════════════════

async def _db_search_companies(domain: str, campaign_purpose: str, db: AsyncSession) -> list[dict]:
    """
    Find companies in the DB matching the domain via:
    - domain_tags fuzzy match
    - sector / industry / product_type / description keyword match
    """
    matched_tags = expand_domain_query(domain)

    # Build OR conditions across multiple fields
    conditions = []

    # domain_tags JSON contains any matched tag
    for tag in matched_tags:
        conditions.append(cast(Company.domain_tags, String).ilike(f"%{tag}%"))

    # sector / industry / product_type / description LIKE match
    for keyword in _extract_keywords(domain + " " + campaign_purpose):
        conditions.append(Company.sector.ilike(f"%{keyword}%"))
        conditions.append(Company.industry.ilike(f"%{keyword}%"))
        conditions.append(Company.product_type.ilike(f"%{keyword}%"))
        conditions.append(Company.description.ilike(f"%{keyword}%"))

    stmt = select(Company).where(or_(*conditions)).order_by(Company.known.asc(), Company.name.asc()).limit(50)
    result = await db.execute(stmt)
    companies = result.scalars().all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "sector": c.sector,
            "product_type": c.product_type,
            "description": c.description,
            "website": c.website,
            "domain_tags": c.domain_tags or [],
            "known": c.known,
            "relevance_reason": _company_relevance_reason(c, domain),
            "match_source": "db_domain_tag",
            "_model": c,
        }
        for c in companies
    ]


async def _db_search_individuals(domain: str, campaign_purpose: str, db: AsyncSession) -> list[dict]:
    """
    Find individuals matching the domain two ways:
    1. Employed at a domain-matched company (via company_id FK)
    2. Personally tagged with domain_tags matching the domain
       (past contribution — even if current employer is unrelated)
    """
    matched_tags = expand_domain_query(domain)
    keywords = _extract_keywords(domain + " " + campaign_purpose)

    conditions = []
    for tag in matched_tags:
        conditions.append(cast(Individual.domain_tags, String).ilike(f"%{tag}%"))
    for keyword in keywords:
        conditions.append(Individual.notes.ilike(f"%{keyword}%"))
        conditions.append(Individual.role.ilike(f"%{keyword}%"))

    stmt = (
        select(Individual)
        .where(or_(*conditions))
        .order_by(Individual.known.asc(), Individual.name.asc())
        .limit(50)
    )
    result = await db.execute(stmt)
    individuals = result.scalars().all()

    return [
        {
            "id": i.id,
            "name": i.name,
            "role": i.role,
            "email": i.email,
            "company_id": i.company_id,
            "company_name": None,  # filled later
            "domain_tags": i.domain_tags or [],
            "known": i.known,
            "relevance_reason": _individual_relevance_reason(i, domain),
            "match_source": "db_personal_tag" if (i.domain_tags and any(
                tag in str(i.domain_tags) for tag in matched_tags
            )) else "db_role_match",
            "_model": i,
        }
        for i in individuals
    ]


# ════════════════════════════════════════════════════════════
#  Layer 2 — Serper Web Discovery
# ════════════════════════════════════════════════════════════

async def _serper_discover_companies(domain: str, campaign_purpose: str) -> list[dict]:
    """
    Use Serper to discover companies in the target domain not yet in the DB.
    Uses LLM to evaluate search results, extract real companies, and generate relevance reasons.
    Falls back to heuristic extraction from Serper results if LLM fails.
    """
    import logging
    logger = logging.getLogger("discovery")

    if not settings.SERPER_API_KEY:
        logger.warning("SERPER_API_KEY not set — skipping web discovery")
        return []

    from app.services.llm_service import call_llm_json

    queries = [
        f"{domain} companies OR startups OR organizations",
        f"{domain} {_short_purpose(campaign_purpose)} companies OR non-profit",
    ]

    all_results = []

    for query in queries:
        result = await serper_service.web_search(query, num=10)
        logger.info(f"Serper query '{query}': status={result.get('status')}, results={len(result.get('organic', []))}")
        if result.get("status") == "ok":
            all_results.extend(result.get("organic", []))

    if not all_results:
        logger.warning("Serper returned 0 results for all queries")
        return []

    # De-duplicate by link
    seen_links = set()
    unique_results = []
    for r in all_results:
        link = r.get("link", "")
        if link not in seen_links:
            seen_links.add(link)
            unique_results.append(r)
    all_results = unique_results

    logger.info(f"Total unique Serper results: {len(all_results)}")

    # Format for LLM (limit to 15 to keep prompt short)
    snippets = []
    for r in all_results[:15]:
        snippets.append(f"- Title: {r.get('title')}\n  URL: {r.get('link')}\n  Snippet: {r.get('snippet')}")

    snippets_text = "\n".join(snippets)

    prompt = f"""Extract companies/organizations from these search results.

Domain: "{domain}"
Campaign purpose: "{campaign_purpose}"

Search results:
{snippets_text}

RULES:
1. Only extract REAL, SINGLE companies, startups, NGOs, foundations, or organizations.
2. Skip news articles, blog posts, listicles (e.g. "5 Startups to watch"), guides, directories (crunchbase, f6s, linkedin).
3. If the search result is an article talking ABOUT multiple companies, DO NOT extract the article itself as a company.
4. Foundations and non-profits ARE valid targets
5. Each company needs: name, website, sector, product_type, relevance_reason

Return ONLY this JSON, nothing else:
{{"companies":[{{"name":"...","website":"...","sector":"...","product_type":"...","relevance_reason":"..."}}]}}"""

    llm_res = await call_llm_json(
        prompt=prompt,
        system_prompt="You are a JSON API. Output ONLY valid JSON. No explanations, no markdown, no text before or after the JSON.",
        required_keys=["companies"],
        max_tokens=2000,
        max_retries=3,
    )

    logger.info(f"LLM result: status={llm_res['status']}, model={llm_res.get('model')}, error={llm_res.get('error')}")

    # Try LLM results first
    if llm_res["status"] == "ok":
        companies_data = llm_res["data"].get("companies", [])
        logger.info(f"LLM extracted {len(companies_data)} companies")
    else:
        # ── Heuristic fallback: extract companies directly from Serper results ──
        logger.warning(f"LLM failed ({llm_res['status']}), using heuristic fallback")
        companies_data = _heuristic_extract_companies(all_results, domain, campaign_purpose)
        logger.info(f"Heuristic extracted {len(companies_data)} companies")

    discovered = {}

    for c in companies_data:
        website = c.get("website", "")
        extracted_domain = _extract_domain_from_url(website)

        if not extracted_domain or _is_generic_domain(extracted_domain):
            continue

        if extracted_domain not in discovered:
            discovered[extracted_domain] = {
                "name": c.get("name"),
                "website": website,
                "description": c.get("relevance_reason"),
                "sector": c.get("sector"),
                "product_type": c.get("product_type"),
                "domain_tags": [domain.lower().replace(" ", "-")],
                "source": "serper_discovery",
                "relevance_reason": c.get("relevance_reason"),
                "match_source": "serper_web",
                "web_domain": extracted_domain,
            }

    logger.info(f"Final discovered companies (after dedup/filter): {len(discovered)}")
    return list(discovered.values())


def _heuristic_extract_companies(
    serper_results: list[dict],
    domain: str,
    campaign_purpose: str,
) -> list[dict]:
    """
    Fallback: extract companies directly from Serper organic results
    when LLM parsing fails. Uses URL domain and title heuristics.
    """
    companies = []

    for item in serper_results:
        link = item.get("link", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        extracted = _extract_domain_from_url(link)
        if not extracted or _is_generic_domain(extracted):
            continue

        # Skip obvious non-company pages
        skip_patterns = [
            "f6s.com", "crunchbase.com", "angel.co", "pitchbook.com",
            "sciencedirect.com", "tandfonline.com", "springer.com",
            "researchgate.net", "academia.edu", "wikipedia.org",
            "reddit.com", "quora.com", "amazon.com",
        ]
        if any(p in extracted for p in skip_patterns):
            continue

        # Skip article/listicle titles
        lower_title = title.lower()
        skip_title_patterns = [
            "top ", " best ", "how to", "guide", " tips",
            "what is", "list of", " vs ", "review", "startups",
            "companies", "brands", "innovative", "trends"
        ]
        if any(p in lower_title for p in skip_title_patterns):
            continue

        # Reject titles that start with a number (e.g., "5 Innovative Precision Fermentation Startups")
        if re.match(r"^\d+\s+", title):
            continue

        name = _extract_company_name(title, extracted)
        relevance = snippet[:150] if snippet else f"Found via web search for '{domain}'"

        companies.append({
            "name": name,
            "website": link.split("?")[0],  # strip query params
            "sector": domain,
            "product_type": domain,
            "relevance_reason": relevance,
        })

    return companies


async def _serper_discover_individuals(domain: str, campaign_purpose: str) -> list[dict]:
    """
    Use Serper to find independent contributors to the domain —
    people who have worked on or advocated for the domain
    regardless of their current employer.
    """
    if not settings.SERPER_API_KEY:
        return []

    query = f"{domain} {_short_purpose(campaign_purpose)} (independent OR freelance OR advocate OR expert) -employee -company"
    result = await serper_service.web_search(query, num=10)
    if result.get("status") != "ok":
        return []

    found = []
    seen_names = set()

    for item in result.get("organic", []):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        name = _extract_person_name_from_snippet(title + " " + snippet)
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        found.append({
            "name": name,
            "role": _extract_role_from_snippet(snippet),
            "description": snippet[:200],
            "domain_tags": [domain.lower().replace(" ", "-")],
            "source": "serper_discovery",
            "relevance_reason": f"Found as domain contributor: {snippet[:120]}",
            "match_source": "serper_individual",
        })

    return found[:5]  # limit to avoid noise


# ════════════════════════════════════════════════════════════
#  Layer 3 — Hunter Contact Discovery at Matched Companies
# ════════════════════════════════════════════════════════════

async def _hunter_discover_contacts(
    company: Company,
    db: AsyncSession,
    existing_individual_ids: set,
) -> list[dict]:
    """
    Use Hunter domain search to find key decision-makers at a company.
    Only fetches senior roles (management, executive, C-level).
    Returns new individuals not already in the DB.
    """
    if not settings.HUNTER_API_KEY or not company.website:
        return []

    domain = _extract_domain_from_url(company.website)
    if not domain:
        return []

    result = await hunter_service.domain_search(domain, department="management", limit=5)
    if result.get("status") != "ok":
        return []

    new_contacts = []
    for contact in result.get("emails", []):
        email = contact.get("email")
        if not email:
            continue

        # Check if already in DB by email
        existing = await db.execute(
            select(Individual).where(Individual.email == email)
        )
        if existing.scalar_one_or_none():
            continue

        first = contact.get("first_name", "")
        last = contact.get("last_name", "")
        name = f"{first} {last}".strip() or email.split("@")[0]

        new_contacts.append({
            "name": name,
            "first_name": first,
            "last_name": last,
            "role": contact.get("position"),
            "email": email,
            "email_confidence": contact.get("confidence", 0),
            "email_verified": contact.get("verified", False),
            "linkedin_url": contact.get("linkedin"),
            "company_id": company.id,
            "domain_tags": company.domain_tags or [],
            "source": "hunter_discovery",
            "relevance_reason": f"Decision-maker at {company.name} — {contact.get('position', 'Contact')}",
            "match_source": "hunter_contact",
        })

    return new_contacts


# ════════════════════════════════════════════════════════════
#  DB Upsert — Save New Companies and Individuals
# ════════════════════════════════════════════════════════════

async def _save_new_company(company_data: dict, db: AsyncSession) -> Optional[Company]:
    """
    Save a newly discovered company to the DB if it doesn't already exist.
    Matches by website domain to avoid duplicates.
    Returns the saved (or existing) Company model.
    """
    website = company_data.get("website", "")
    name = company_data.get("name", "")

    if not name:
        return None

    # Check by website domain
    if website:
        web_domain = _extract_domain_from_url(website)
        existing = await db.execute(
            select(Company).where(Company.website.ilike(f"%{web_domain}%"))
        )
        found = existing.scalar_one_or_none()
        if found:
            return found

    # Check by name (fuzzy)
    existing_by_name = await db.execute(
        select(Company).where(Company.name.ilike(name))
    )
    found_by_name = existing_by_name.scalar_one_or_none()
    if found_by_name:
        return found_by_name

    # Create new
    company = Company(
        name=name,
        website=website or None,
        description=company_data.get("description"),
        sector=company_data.get("sector"),
        product_type=company_data.get("product_type"),
        domain_tags=company_data.get("domain_tags", []),
        source=company_data.get("source", "serper_discovery"),
    )
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


async def _save_new_individual(individual_data: dict, db: AsyncSession) -> Optional[Individual]:
    """
    Save a newly discovered individual to the DB.
    Skips if already exists by email.
    """
    name = individual_data.get("name", "")
    email = individual_data.get("email")

    if not name:
        return None

    # Deduplicate by email
    if email:
        existing = await db.execute(select(Individual).where(Individual.email == email))
        if existing.scalar_one_or_none():
            return None

    # Deduplicate by name + company
    company_id = individual_data.get("company_id")
    if company_id:
        existing_by_name = await db.execute(
            select(Individual).where(
                Individual.name.ilike(name),
                Individual.company_id == company_id,
            )
        )
        if existing_by_name.scalar_one_or_none():
            return None

    individual = Individual(
        name=name,
        first_name=individual_data.get("first_name"),
        last_name=individual_data.get("last_name"),
        role=individual_data.get("role"),
        email=email,
        email_confidence=individual_data.get("email_confidence"),
        email_verified=individual_data.get("email_verified", False),
        linkedin_url=individual_data.get("linkedin_url"),
        company_id=company_id,
        domain_tags=individual_data.get("domain_tags", []),
        source=individual_data.get("source", "serper_discovery"),
    )
    db.add(individual)
    await db.flush()
    await db.refresh(individual)
    return individual


# ════════════════════════════════════════════════════════════
#  Background Enrichment
# ════════════════════════════════════════════════════════════

async def enrich_discovered_targets(company_ids: list[str], individual_ids: list[str]):
    """
    Background task: run all enrichment services on newly discovered targets.
    Uses its own DB session since the request session has already closed.

    Enrichment per company: Serper news/web + OpenCorporates + Hunter contacts
    Enrichment per individual: Serper mentions + Hunter email + Humantic personality
    """
    async with AsyncSessionLocal() as db:
        # ── Enrich companies ──────────────────────────────────
        for company_id in company_ids:
            try:
                result = await db.execute(select(Company).where(Company.id == company_id))
                company = result.scalar_one_or_none()
                if not company:
                    continue

                await serper_service.enrich_company(company, db)
                await asyncio.sleep(0.3)

                if settings.OPENCORPORATES_API_TOKEN:
                    await opencorporates_service.enrich_company(company, db)
                    await asyncio.sleep(0.3)

                if settings.HUNTER_API_KEY:
                    await hunter_service.enrich_company_contacts(company, db)
                    await asyncio.sleep(0.3)

                await db.commit()
            except Exception:
                await db.rollback()

        # ── Enrich individuals ────────────────────────────────
        for individual_id in individual_ids:
            try:
                result = await db.execute(
                    select(Individual).where(Individual.id == individual_id)
                )
                individual = result.scalar_one_or_none()
                if not individual:
                    continue

                await serper_service.enrich_individual(individual, db)
                await asyncio.sleep(0.3)

                if settings.HUNTER_API_KEY:
                    await hunter_service.enrich_individual_email(individual, db)
                    await asyncio.sleep(0.2)

                if settings.HUMANTIC_API_KEY and individual.linkedin_url:
                    await humantic_service.enrich_individual(individual, db)
                    await asyncio.sleep(0.3)

                await db.commit()
            except Exception:
                await db.rollback()


# ════════════════════════════════════════════════════════════
#  Main Discovery Orchestrator
# ════════════════════════════════════════════════════════════

async def discover_targets(
    domain: str,
    campaign_purpose: str,
    db: AsyncSession,
    limit: int = 30,
) -> dict:
    """
    Full discovery pipeline:
    1. DB search for existing matching companies + individuals
    2. Serper live web search for new companies
    3. Save new companies to DB
    4. Hunter contact discovery at matched companies
    5. Save new individuals to DB
    6. Return merged, deduplicated results

    Returns:
        {
            "domain": str,
            "campaign_purpose": str,
            "companies": [DiscoveredCompany],
            "individuals": [DiscoveredIndividual],
            "new_company_ids": list[str],   ← for background enrichment
            "new_individual_ids": list[str], ← for background enrichment
        }
    """
    new_company_ids = []
    new_individual_ids = []
    seen_company_ids = set()
    seen_individual_ids = set()

    companies_out = []
    individuals_out = []

    # ── Step 1: DB search ─────────────────────────────────────
    db_companies = await _db_search_companies(domain, campaign_purpose, db)
    db_individuals = await _db_search_individuals(domain, campaign_purpose, db)

    for c in db_companies:
        if c["id"] not in seen_company_ids:
            seen_company_ids.add(c["id"])
            companies_out.append(c)

    for i in db_individuals:
        if i["id"] not in seen_individual_ids:
            seen_individual_ids.add(i["id"])
            individuals_out.append(i)

    # ── Step 2: Serper company discovery ─────────────────────
    if settings.SERPER_API_KEY:
        serper_companies = await _serper_discover_companies(domain, campaign_purpose)

        for sc in serper_companies:
            saved = await _save_new_company(sc, db)
            if saved and saved.id not in seen_company_ids:
                seen_company_ids.add(saved.id)
                new_company_ids.append(saved.id)
                companies_out.append({
                    "id": saved.id,
                    "name": saved.name,
                    "sector": saved.sector,
                    "product_type": saved.product_type,
                    "description": saved.description or sc.get("description"),
                    "website": saved.website,
                    "domain_tags": saved.domain_tags or [],
                    "known": saved.known,
                    "relevance_reason": sc.get("relevance_reason", f"Discovered via web search for '{domain}'"),
                    "match_source": sc.get("match_source", "serper_web"),
                    "_model": saved,
                })

        await db.commit()

    # ── Step 3: Hunter contact discovery ─────────────────────
    if settings.HUNTER_API_KEY:
        for company_entry in companies_out[:15]:  # limit Hunter calls
            company_model = company_entry.get("_model")
            if not company_model:
                continue

            contacts = await _hunter_discover_contacts(
                company_model, db, seen_individual_ids
            )
            for contact in contacts:
                saved_ind = await _save_new_individual(contact, db)
                if saved_ind and saved_ind.id not in seen_individual_ids:
                    seen_individual_ids.add(saved_ind.id)
                    new_individual_ids.append(saved_ind.id)
                    individuals_out.append({
                        "id": saved_ind.id,
                        "name": saved_ind.name,
                        "role": saved_ind.role,
                        "email": saved_ind.email,
                        "company_id": saved_ind.company_id,
                        "company_name": company_entry["name"],
                        "domain_tags": saved_ind.domain_tags or [],
                        "known": saved_ind.known,
                        "relevance_reason": contact.get("relevance_reason"),
                        "match_source": "hunter_contact",
                        "_model": saved_ind,
                    })

        await db.commit()

    # ── Step 4: Resolve company names for individuals ─────────
    company_name_map = {c["id"]: c["name"] for c in companies_out}
    for ind in individuals_out:
        if not ind.get("company_name") and ind.get("company_id"):
            ind["company_name"] = company_name_map.get(ind["company_id"])
            if not ind["company_name"]:
                # Lookup in DB
                comp_result = await db.execute(
                    select(Company.name).where(Company.id == ind["company_id"])
                )
                ind["company_name"] = comp_result.scalar_one_or_none()

    # ── Step 5: Trim to limit, strip internal _model keys ─────
    def _clean(entry: dict) -> dict:
        return {k: v for k, v in entry.items() if k != "_model"}

    companies_final = [_clean(c) for c in companies_out[:limit]]
    individuals_final = [_clean(i) for i in individuals_out[:limit]]

    return {
        "domain": domain,
        "campaign_purpose": campaign_purpose,
        "companies": companies_final,
        "individuals": individuals_final,
        "total_companies": len(companies_final),
        "total_individuals": len(individuals_final),
        "new_company_ids": new_company_ids,
        "new_individual_ids": new_individual_ids,
    }


# ════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════

def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from free-form text for DB LIKE matching."""
    stop_words = {"the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "at",
                  "with", "by", "is", "are", "we", "our", "that", "this", "it"}
    words = re.sub(r"[^a-z0-9\s-]", "", text.lower()).split()
    return [w for w in words if len(w) > 3 and w not in stop_words][:8]


def _short_purpose(purpose: str) -> str:
    """Trim campaign purpose to first 5 words for search queries."""
    words = purpose.strip().split()
    return " ".join(words[:5])


def _extract_domain_from_url(url: str) -> Optional[str]:
    """Extract bare domain from a URL. https://www.beyondmeat.com/page → beyondmeat.com"""
    if not url:
        return None
    url = url.strip().lower()
    for prefix in ("https://", "http://", "www."):
        url = url.removeprefix(prefix)
    domain = url.split("/")[0].split("?")[0]
    return domain if "." in domain else None


_GENERIC_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "instagram.com",
    "youtube.com", "wikipedia.org", "bloomberg.com", "reuters.com",
    "techcrunch.com", "forbes.com", "medium.com", "crunchbase.com",
    "angel.co", "glassdoor.com", "indeed.com", "google.com",
    "f6s.com", "pitchbook.com", "sciencedirect.com", "tandfonline.com",
    "springer.com", "researchgate.net", "academia.edu", "reddit.com",
    "quora.com", "amazon.com", "bimpactassessment.net", "x.com",
    "tiktok.com", "pinterest.com", "yelp.com", "bbb.org",
}

def _is_generic_domain(domain: str) -> bool:
    """Returns True if the domain is a known generic/news site (not a company)."""
    return any(domain.endswith(g) for g in _GENERIC_DOMAINS)


def _extract_company_name(title: str, domain: str) -> str:
    """
    Best-effort company name extraction from a page title.
    Falls back to capitalizing the domain root.
    """
    # Common patterns: "Company Name - Tagline", "Company Name | About"
    for sep in [" - ", " | ", " – ", " — "]:
        if sep in title:
            candidate = title.split(sep)[0].strip()
            if 2 < len(candidate) < 60:
                return candidate
    # Fallback: prettify domain root
    root = domain.split(".")[0]
    return root.replace("-", " ").title()


def _extract_person_name_from_snippet(text: str) -> Optional[str]:
    """Very basic heuristic: look for 'FirstName LastName' pattern in text."""
    match = re.search(r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b', text)
    return match.group(1) if match else None


def _extract_role_from_snippet(text: str) -> Optional[str]:
    """Extract likely job title from snippet text."""
    roles = ["CEO", "Founder", "Director", "President", "Manager", "Officer",
             "Head", "VP", "Co-founder", "Chief", "Lead", "Advocate"]
    for role in roles:
        if role.lower() in text.lower():
            return role
    return None


def _company_relevance_reason(company: Company, domain: str) -> str:
    if company.description:
        return company.description[:120]
    if company.product_type:
        return f"{company.product_type} — matched domain '{domain}'"
    return f"Matched domain '{domain}' via {company.sector or 'sector'}"


def _individual_relevance_reason(individual: Individual, domain: str) -> str:
    if individual.notes:
        return individual.notes[:120]
    if individual.role:
        return f"{individual.role} — domain contribution in '{domain}'"
    return f"Tagged with domain '{domain}'"
