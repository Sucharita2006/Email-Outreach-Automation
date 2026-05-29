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

    # Split comma-separated domains into individual search terms
    domain_parts = [d.strip() for d in domain.split(",") if d.strip()]
    combined_domain = " ".join(domain_parts)  # "plant-based veganism"

    # Build targeted queries — one set per domain term + combined queries
    queries = []
    for dp in domain_parts[:3]:  # max 3 domain terms
        queries.append(f"{dp} companies OR startups")
    queries.append(f"top {combined_domain} companies list")
    if campaign_purpose:
        queries.append(f"{combined_domain} {_short_purpose(campaign_purpose)} companies")
    queries = queries[:5]  # cap at 5 queries total

    # ── Parallel Serper queries ──
    search_tasks = [serper_service.web_search(q, num=10) for q in queries]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    all_results = []
    for query, result in zip(queries, search_results):
        if isinstance(result, Exception):
            logger.error(f"Serper query failed '{query}': {result}")
            continue
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

    # Format snippets
    snippets = []
    for r in all_results[:20]:
        snippets.append(f"- Title: {r.get('title')}\n  URL: {r.get('link')}\n  Snippet: {r.get('snippet')}")
    snippets_text = "\n".join(snippets)

    # ── Parallel listicle scraping ──
    listicle_texts = ""
    listicle_candidates = [r for r in all_results if "top" in r.get("title", "").lower() or "list" in r.get("title", "").lower()][:2]
    if listicle_candidates:
        logger.info(f"Fetching full text from {len(listicle_candidates)} listicle candidates (parallel)...")
        scrape_tasks = [_fetch_page_text(r.get("link")) for r in listicle_candidates]
        scrape_results = await asyncio.gather(*scrape_tasks, return_exceptions=True)
        for r, text in zip(listicle_candidates, scrape_results):
            if isinstance(text, Exception) or not text:
                continue
            listicle_texts += f"\n\n--- ARTICLE TEXT FROM: {r.get('link')} ---\n{text}\n"

    prompt = f"""You are a company extraction engine. Your job is to extract REAL companies/organizations from search results and article texts.

Domain: "{domain}"
Campaign purpose: "{campaign_purpose}"

Search Result Snippets:
{snippets_text}
{listicle_texts}

STRICT RULES — read very carefully:
1. Extract ONLY real companies, startups, brands, or organizations that are actual businesses operating in this domain.
2. Even if they are found inside an article/listicle, extract the COMPANY itself — NOT the article, NOT the website hosting the list.
3. The "name" must be the company's actual brand/legal name (e.g. "Beyond Meat", "Oatly", "Impossible Foods").
4. The "relevance_reason" MUST be a specific 2-3 sentence description of what the company does and why it fits the domain.
5. If the website is not explicitly in the text, guess their standard homepage URL (e.g. https://companyname.com). Do NOT return the article/listicle URL.

YOU MUST REJECT (do NOT include any of these):
- FAQ pages, blog posts, articles, reports, guides, or listicle titles (e.g. "General FAQs", "Top 10 Vegan Companies")
- Stock trackers, ETF pages, or investment databases (e.g. "Vegan Stocks + ETFs")
- News websites, directories, databases, or aggregator platforms
- Wikipedia pages, Reddit threads, or forum posts
- Generic phrases that are not company names (e.g. "Veganism Around The World", "Plant-Based Diet Guide")
- Any name that contains words like: FAQ, guide, list, top, best, report, review, article, stocks, ETF, wiki, how to

Return ONLY this JSON:
{{"companies":[{{"name":"ActualCompanyName","website":"https://company-homepage.com","sector":"...","product_type":"...","relevance_reason":"2-3 sentences: what they do + why they fit"}}]}}

If NO valid companies are found, return: {{"companies":[]}}"""

    llm_res = await call_llm_json(
        prompt=prompt,
        system_prompt="You are a strict company extraction API. Output ONLY valid JSON. You MUST only extract real companies with their own product/service — never articles, listicles, directories, FAQ pages, stock trackers, reports, or blogs. Each name must be an actual registered business or brand name.",
        required_keys=["companies"],
        max_tokens=3000,
        max_retries=3,
    )

    logger.info(f"LLM result: status={llm_res['status']}, model={llm_res.get('model')}, error={llm_res.get('error')}")

    # Try LLM results first
    if llm_res["status"] == "ok":
        companies_data = llm_res["data"].get("companies", [])
        logger.info(f"LLM extracted {len(companies_data)} companies (pre-validation)")
    else:
        # ── Heuristic fallback: extract companies directly from Serper results ──
        logger.warning(f"LLM failed ({llm_res['status']}), using heuristic fallback")
        companies_data = _heuristic_extract_companies(all_results, domain, campaign_purpose)
        logger.info(f"Heuristic extracted {len(companies_data)} companies")

    # ── Post-LLM validation: reject anything that slipped through ──
    validated = []
    for c in companies_data:
        name = (c.get("name") or "").strip()
        website = (c.get("website") or "").strip()

        if not name or not website:
            continue

        # Reject if name looks like an article/directory/listicle
        if _is_non_company_name(name):
            logger.info(f"Rejected non-company name: '{name}'")
            continue

        # Reject if website points to a known generic/aggregator domain
        extracted_domain = _extract_domain_from_url(website)
        if not extracted_domain or _is_generic_domain(extracted_domain):
            logger.info(f"Rejected generic domain: '{extracted_domain}' for '{name}'")
            continue

        validated.append(c)

    logger.info(f"Post-validation: {len(validated)} companies remain (from {len(companies_data)})")

    discovered = {}

    for c in validated:
        website = c.get("website", "")
        extracted_domain = _extract_domain_from_url(website)

        if extracted_domain not in discovered:
            relevance = c.get("relevance_reason", "")
            # Ensure the description is a proper sentence, not a raw snippet
            if relevance and len(relevance) < 10:
                relevance = f"Operates in the {domain} sector."

            discovered[extracted_domain] = {
                "name": c.get("name"),
                "website": website,
                "description": relevance,
                "sector": c.get("sector"),
                "product_type": c.get("product_type"),
                "domain_tags": [d.strip().lower().replace(" ", "-") for d in domain.split(",") if d.strip()],
                "source": "serper_discovery",
                "relevance_reason": relevance,
                "match_source": "serper_web",
                "web_domain": extracted_domain,
            }

    logger.info(f"Final discovered companies (after dedup/filter): {len(discovered)}")
    return list(discovered.values())


def _is_non_company_name(name: str) -> bool:
    """
    Returns True if the name looks like an article, listicle, directory,
    or database page rather than a real company name.
    """
    lower = name.lower()

    # Starts with a number → almost always a listicle ("71+ Fundraising Ideas")
    if re.match(r"^\d+[\s\+\-]", name):
        return True

    # Contains explicit non-company keywords (word-boundary match to avoid false positives)
    reject_patterns = [
        r"\bdatabase\b", r"\bdirectory\b", r"\blist of\b", r"\bmembers\b",
        r"\bportfolio\b", r"\bguide\b", r"\bideas\b",
        r"\bhow to\b", r"\bwhat is\b", r"\btips for\b", r"\b vs \b", r"\breview\b",
        r"\bcompanies\b", r"\bstartups\b", r"\borganizations\b", r"\bbrands\b",
        r"\btrends\b", r"\breport\b", r"\branking\b", r"\btracker\b",
        r"\bresources\b", r"\btools for\b",
        r"\blandscape\b", r"\becosystem\b", r"\bmarket map\b", r"\boverview\b",
        r"\bcomparison\b", r"\bspotlight\b",
        r"\bwinners\b", r"\bfinalists\b",
        r"\bfaq\b", r"\bfaqs\b", r"\bstocks\b", r"\betf\b", r"\baround the world\b", r"\bstatistics\b",
        r"^top \d+", r"^best \d+",
    ]
    if any(re.search(p, lower) for p in reject_patterns):
        return True

    # Too long to be a company name (likely an article title)
    if len(name) > 80:
        return True

    # Contains year pattern in parentheses like "Alternative protein (2026)"
    if re.search(r"\(\d{4}\)", name):
        return True

    return False


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

        # Skip if URL path is deep (articles tend to have long paths)
        path = link.split(extracted)[-1] if extracted in link else ""
        if path.count("/") > 2:
            continue

        # Skip if title looks like a non-company page
        if _is_non_company_name(title):
            continue

        name = _extract_company_name(title, extracted)

        # Also validate the extracted name
        if _is_non_company_name(name):
            continue

        relevance = snippet[:150] if snippet else f"Found via web search for '{domain}'"

        companies.append({
            "name": name,
            "website": f"https://{extracted}",  # point to homepage, not deep link
            "sector": domain,
            "product_type": domain,
            "relevance_reason": relevance,
        })

    return companies


async def _serper_discover_individuals(domain: str, campaign_purpose: str) -> list[dict]:
    """
    Use Serper + LLM to find independent individuals who are influential
    in the domain — activists, authors, researchers, advocates, consultants,
    regardless of their current employer.
    """
    import logging
    logger = logging.getLogger("discovery")

    if not settings.SERPER_API_KEY:
        return []

    from app.services.llm_service import call_llm_json

    # Split comma-separated domains into individual search terms
    domain_parts = [d.strip() for d in domain.split(",") if d.strip()]
    combined_domain = " ".join(domain_parts)

    queries = []
    for dp in domain_parts[:3]:
        queries.append(f"{dp} influential people leaders advocates")
    queries.append(f"top {combined_domain} activists influencers list")
    if campaign_purpose:
        queries.append(f"{combined_domain} {_short_purpose(campaign_purpose)} expert researcher author")
    queries = queries[:5]


    # ── Parallel Serper queries ──
    search_tasks = [serper_service.web_search(q, num=10) for q in queries]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    all_results = []
    for query, result in zip(queries, search_results):
        if isinstance(result, Exception):
            logger.error(f"Individual Serper query failed '{query}': {result}")
            continue
        logger.info(f"Individual Serper query '{query}': results={len(result.get('organic', []))}")
        if result.get("status") == "ok":
            all_results.extend(result.get("organic", []))

    if not all_results:
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

    # Build snippets
    snippets = []
    for r in all_results[:20]:
        snippets.append(f"- Title: {r.get('title')}\n  URL: {r.get('link')}\n  Snippet: {r.get('snippet')}")
    snippets_text = "\n".join(snippets)

    # ── Parallel listicle scraping ──
    listicle_texts = ""
    listicle_keywords = ["top", "list", "influential", "famous", "notable", "best", "leading"]
    listicle_candidates = [r for r in all_results if any(kw in r.get("title", "").lower() for kw in listicle_keywords)][:2]
    if listicle_candidates:
        logger.info(f"Fetching full text from {len(listicle_candidates)} individual listicle candidates (parallel)...")
        scrape_tasks = [_fetch_page_text(r.get("link")) for r in listicle_candidates]
        scrape_results = await asyncio.gather(*scrape_tasks, return_exceptions=True)
        for r, text in zip(listicle_candidates, scrape_results):
            if isinstance(text, Exception) or not text:
                continue
            listicle_texts += f"\n\n--- ARTICLE TEXT FROM: {r.get('link')} ---\n{text}\n"

    prompt = f"""You are an individual person extraction engine. Your job is to extract REAL, LIVING, CURRENTLY ACTIVE PEOPLE who are influential in a domain AND who can be contacted via email at their organization.

Domain: "{domain}"
Campaign purpose: "{campaign_purpose}"

Search Result Snippets:
{snippets_text}
{listicle_texts}

STRICT RULES:
1. PRIORITIZE people who work at ORGANIZATIONS, NONPROFITS, COMPANIES, or INSTITUTIONS. We need people with professional email addresses, not celebrities.
2. ONLY extract people who are ALIVE and CURRENTLY ACTIVE today. Do NOT include deceased people, historical figures, or anyone who died before 2020.
3. These should be executives, directors, founders, researchers, program managers, coordinators, or advocates who work at SPECIFIC organizations.
4. Each person MUST have a full name (first + last name). Skip anyone where you only have a first name.
5. Do NOT include generic roles like "Sales", "Contact", "Info", "Support".
6. Do NOT include celebrities or actors (e.g., no Joaquin Phoenix, no Ellen DeGeneres) unless they FOUNDED an organization in this domain.
7. The "role" should describe what they currently do at their organization.
8. "company_name" MUST be the name of the organization/company they work at. This is REQUIRED — skip the person if you don't know their organization.
9. "company_website" should be the organization's website URL (e.g. "https://example.org"). This is very important for finding their email.
10. "email" — if you know their email address from the search results, include it. Otherwise set to null.
11. The "relevance_reason" MUST be 2-3 detailed sentences explaining who they are and why they matter.

Return ONLY this JSON:
{{"individuals":[{{"name":"Full Name","role":"Their title at their organization","company_name":"Organization Name","company_website":"https://org-website.com","email":null,"relevance_reason":"2-3 sentences","linkedin_url":null}}]}}

If NO valid individuals are found, return: {{"individuals":[]}}"""

    llm_res = await call_llm_json(
        prompt=prompt,
        system_prompt="You are an expert people researcher. Output ONLY valid JSON. Extract ONLY real, living, currently active individuals — never deceased or historical figures. Never include generic contact roles like 'Sales' or 'Info'.",
        required_keys=["individuals"],
        max_tokens=4000,
        max_retries=3,
    )

    logger.info(f"Individual LLM result: status={llm_res['status']}, model={llm_res.get('model')}")

    if llm_res["status"] != "ok":
        logger.warning(f"Individual LLM failed: {llm_res.get('error')}")
        return []

    individuals_data = llm_res["data"].get("individuals", [])
    logger.info(f"LLM extracted {len(individuals_data)} individuals")

    found = []
    seen_names = set()
    for ind in individuals_data:
        name = (ind.get("name") or "").strip()
        if not name or name.lower() in seen_names:
            continue
        # Basic validation: must look like a person name (2+ words)
        if len(name.split()) < 2:
            continue
        seen_names.add(name.lower())

        # Split name into first/last
        parts = name.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:])

        found.append({
            "name": name,
            "first_name": first_name,
            "last_name": last_name,
            "role": ind.get("role", "Domain expert"),
            "email": ind.get("email"),
            "description": ind.get("relevance_reason", ""),
            "domain_tags": [d.strip().lower().replace(" ", "-") for d in domain.split(",") if d.strip()],
            "source": "serper_discovery",
            "relevance_reason": ind.get("relevance_reason", f"Influential figure in {domain}"),
            "match_source": "serper_individual",
            "linkedin_url": ind.get("linkedin_url"),
            "company_name": ind.get("company_name"),
            "company_website": ind.get("company_website"),
        })

    return found[:5]  # return up to 5 individuals


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
    print(f"[HUNTER] _hunter_discover_contacts called for: {company.name}")
    print(f"[HUNTER]   website={company.website}, HUNTER_API_KEY set={bool(settings.HUNTER_API_KEY)}")

    if not settings.HUNTER_API_KEY or not company.website:
        print(f"[HUNTER]   SKIP: no API key or no website")
        return []

    domain = _extract_domain_from_url(company.website)
    print(f"[HUNTER]   extracted domain: {domain}")
    if not domain:
        print(f"[HUNTER]   SKIP: could not extract domain")
        return []

    print(f"[HUNTER]   calling domain_search({domain}, department='management', limit=5)")
    result = await hunter_service.domain_search(domain, department="management", limit=5)
    print(f"[HUNTER]   result status={result.get('status')}, emails={len(result.get('emails', []))}, error={result.get('error')}")

    if result.get("status") != "ok" or not result.get("emails"):
        print(f"[HUNTER]   fallback: calling domain_search({domain}, limit=5) without department")
        result = await hunter_service.domain_search(domain, limit=5)
        print(f"[HUNTER]   fallback result status={result.get('status')}, emails={len(result.get('emails', []))}, error={result.get('error')}")

    if result.get("status") != "ok":
        print(f"[HUNTER]   FAIL: status not ok, returning []")
        return []

    # Generic email prefixes that are NOT real people
    _GENERIC_PREFIXES = {
        "sales", "info", "contact", "hello", "support", "admin", "team",
        "press", "media", "marketing", "hr", "careers", "jobs", "office",
        "general", "enquiries", "inquiries", "help", "service", "billing",
        "feedback", "partnerships", "legal", "compliance", "privacy",
        "webmaster", "postmaster", "noreply", "no-reply", "newsletter",
    }

    new_contacts = []
    for contact in result.get("emails", []):
        email = contact.get("email")
        if not email:
            continue

        # Skip generic/non-person emails
        email_prefix = email.split("@")[0].lower()
        if email_prefix in _GENERIC_PREFIXES:
            print(f"[HUNTER]   SKIP generic: {email}")
            continue

        # Check if already in DB by email
        existing = await db.execute(
            select(Individual).where(Individual.email == email)
        )
        if existing.scalar_one_or_none():
            print(f"[HUNTER]   SKIP existing: {email}")
            continue

        first = contact.get("first_name", "")
        last = contact.get("last_name", "")
        name = f"{first} {last}".strip()

        # Skip if no real name (only email prefix as name)
        if not name or len(name.split()) < 2:
            print(f"[HUNTER]   SKIP no real name: {email} (name='{name}')")
            continue

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

    print(f"[HUNTER]   RESULT: {len(new_contacts[:2])} new contacts for {company.name}")
    return new_contacts[:2]


# ════════════════════════════════════════════════════════════
#  Layer 3b — Free Email Discovery (no API key needed)
# ════════════════════════════════════════════════════════════

async def _scrape_website_emails(website: str) -> list[str]:
    """
    Scrape a company's website for email addresses.
    Checks the homepage, /contact, /about, and /team pages.
    Returns a list of unique email addresses found.
    """
    import re as _re
    emails_found = set()
    domain = _extract_domain_from_url(website)
    if not domain:
        return []

    base = f"https://{domain}"
    pages_to_check = [
        base,
        f"{base}/contact",
        f"{base}/contact-us",
        f"{base}/about",
        f"{base}/about-us",
        f"{base}/team",
        f"{base}/our-team",
    ]

    email_pattern = _re.compile(
        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    )

    # Blacklisted email patterns (not real contacts)
    blacklist = {"example.com", "sentry.io", "wixpress.com", "googleapis.com",
                 "w3.org", "schema.org", "facebook.com", "twitter.com",
                 "wordpress.org", "gravatar.com", "cloudflare.com"}

    for url in pages_to_check:
        try:
            text = await _fetch_page_text(url)
            if not text:
                continue
            found = email_pattern.findall(text)
            for email in found:
                email_domain = email.split("@")[1].lower()
                if email_domain not in blacklist and not email.endswith(".png") and not email.endswith(".jpg"):
                    emails_found.add(email.lower())
        except Exception:
            continue

    # Prioritize emails from the company's own domain
    own_domain_emails = [e for e in emails_found if domain in e]
    other_emails = [e for e in emails_found if domain not in e]

    return own_domain_emails + other_emails


async def _serper_find_email(name: str, context: str = "") -> list[str]:
    """
    Use Serper to search Google for email addresses associated with a name.
    Works for both companies and individuals.
    """
    import re as _re
    if not settings.SERPER_API_KEY:
        return []

    query = f'"{name}" email contact {context}'.strip()
    result = await serper_service.web_search(query, num=5)
    if result.get("status") != "ok":
        return []

    email_pattern = _re.compile(
        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    )

    emails_found = set()
    blacklist = {"example.com", "sentry.io", "wixpress.com", "googleapis.com",
                 "w3.org", "schema.org"}

    for item in result.get("organic", []):
        text = f"{item.get('title', '')} {item.get('snippet', '')}"
        found = email_pattern.findall(text)
        for email in found:
            email_domain = email.split("@")[1].lower()
            if email_domain not in blacklist:
                emails_found.add(email.lower())

    return list(emails_found)


async def _discover_company_contacts_free(
    company: Company,
    db: AsyncSession,
    existing_individual_ids: set,
) -> list[dict]:
    """
    Free fallback: scrape the company website + search Google for contact emails.
    No API key required beyond Serper (which we already have).
    Returns contacts in the same format as _hunter_discover_contacts.
    """
    import logging
    logger = logging.getLogger("discovery")

    if not company.website:
        return []

    domain = _extract_domain_from_url(company.website)
    if not domain:
        return []

    # Method 1: Scrape website pages for emails
    emails = await _scrape_website_emails(company.website)
    logger.info(f"  Website scrape for {company.name}: found {len(emails)} emails")

    # Method 2: Serper search for company emails
    if not emails:
        emails = await _serper_find_email(company.name, domain)
        logger.info(f"  Serper email search for {company.name}: found {len(emails)} emails")

    if not emails:
        return []

    new_contacts = []
    for email in emails[:2]:  # limit to 2 contacts per company
        # Check if already in DB
        existing = await db.execute(
            select(Individual).where(Individual.email == email)
        )
        if existing.scalar_one_or_none():
            continue

        # Try to extract a name from the email
        local_part = email.split("@")[0]
        if "." in local_part:
            parts = local_part.split(".")
            name = " ".join(p.capitalize() for p in parts)
        elif local_part in ("info", "contact", "hello", "team", "press", "media", "partnerships", "support"):
            name = f"{company.name} Team"
        else:
            name = local_part.capitalize()

        new_contacts.append({
            "name": name,
            "first_name": name.split()[0] if " " in name else name,
            "last_name": name.split()[-1] if " " in name else "",
            "role": "Contact",
            "email": email,
            "email_confidence": 50,
            "email_verified": False,
            "linkedin_url": None,
            "company_id": company.id,
            "domain_tags": company.domain_tags or [],
            "source": "website_scrape",
            "relevance_reason": f"Contact at {company.name}",
            "match_source": "website_scrape",
        })

    return new_contacts


# ════════════════════════════════════════════════════════════
#  DB Upsert — Save New Companies and Individuals
# ════════════════════════════════════════════════════════════

async def _save_new_company(company_data: dict, db: AsyncSession, campaign_id: Optional[str] = None) -> Optional[Company]:
    """
    Save a newly discovered company to the DB if it doesn't already exist.
    Matches by website domain to avoid duplicates.
    Returns the saved (or existing) Company model.
    """
    website = company_data.get("website", "")
    name = company_data.get("name", "")

    if not name:
        return None

    # Reject non-company names before saving
    if _is_non_company_name(name):
        import logging
        logging.getLogger("discovery").info(f"Rejected non-company name before save: '{name}'")
        return None

    # Check by website domain
    if website:
        web_domain = _extract_domain_from_url(website)
        existing = await db.execute(
            select(Company).where(Company.website.ilike(f"%{web_domain}%"))
        )
        found = existing.scalar_one_or_none()
        if found:
            if campaign_id and campaign_id not in (found.campaign_ids or []):
                found.campaign_ids = list((found.campaign_ids or [])) + [campaign_id]
            return found

    # Check by name (fuzzy)
    existing_by_name = await db.execute(
        select(Company).where(Company.name.ilike(name))
    )
    found_by_name = existing_by_name.scalar_one_or_none()
    if found_by_name:
        if campaign_id and campaign_id not in (found_by_name.campaign_ids or []):
            found_by_name.campaign_ids = list((found_by_name.campaign_ids or [])) + [campaign_id]
        return found_by_name

    # Create new
    company = Company(
        name=name,
        website=website or None,
        description=company_data.get("description"),
        sector=company_data.get("sector"),
        product_type=company_data.get("product_type"),
        domain_tags=company_data.get("domain_tags", []),
        campaign_ids=[campaign_id] if campaign_id else [],
        source=company_data.get("source", "serper_discovery"),
    )
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


async def _save_new_individual(individual_data: dict, db: AsyncSession, campaign_id: Optional[str] = None) -> Optional[Individual]:
    """
    Save a newly discovered individual to the DB.
    Skips if already exists by email.
    """
    name = individual_data.get("name", "").strip()
    email = individual_data.get("email")

    if not name:
        return None

    # Reject junk names
    lower_name = name.lower()
    # "None None" from null first/last names
    if lower_name in ("none none", "none", "", "unknown", "n/a"):
        return None
    # Must be at least 2 words (first + last name)
    if len(name.split()) < 2:
        return None
    # Reject generic team/department names
    _GENERIC_NAME_SUFFIXES = {"team", "support", "staff", "department", "group", "committee"}
    if any(name.lower().endswith(f" {s}") for s in _GENERIC_NAME_SUFFIXES):
        return None

    # Deduplicate by email
    if email:
        existing = await db.execute(select(Individual).where(Individual.email == email))
        found = existing.scalar_one_or_none()
        if found:
            if campaign_id and campaign_id not in (found.campaign_ids or []):
                found.campaign_ids = list((found.campaign_ids or [])) + [campaign_id]
            return found

    # Deduplicate by name
    company_id = individual_data.get("company_id")
    if company_id:
        existing_by_name = await db.execute(
            select(Individual).where(
                Individual.name.ilike(name),
                Individual.company_id == company_id,
            )
        )
    else:
        existing_by_name = await db.execute(
            select(Individual).where(Individual.name.ilike(name))
        )
        
    found_by_name = existing_by_name.scalars().first()
    if found_by_name:
        if campaign_id and campaign_id not in (found_by_name.campaign_ids or []):
            found_by_name.campaign_ids = list((found_by_name.campaign_ids or [])) + [campaign_id]
        return found_by_name

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
        campaign_ids=[campaign_id] if campaign_id else [],
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
    campaign_id: Optional[str] = None,
) -> dict:
    """
    Parallelized discovery pipeline:

    Phase 1: DB search (instant)
    Phase 2: Serper company + individual discovery (PARALLEL)
    Phase 3: Save companies → Hunter contacts (PARALLEL batches of 5)
    Phase 4: Free email fallback (PARALLEL, top 5 companies)
    Phase 5: Resolve names + build response

    Typical completion: ~30-60 seconds (vs 10-15 min sequential).
    """
    import logging
    import time
    logger = logging.getLogger("discovery")
    t_start = time.time()

    new_company_ids = []
    new_individual_ids = []
    seen_company_ids = set()
    seen_individual_ids = set()

    companies_out = []
    individuals_out = []

    # ═══════════════════════════════════════════════════════════
    #  Phase 1: DB search (instant)
    # ═══════════════════════════════════════════════════════════
    db_companies = await _db_search_companies(domain, campaign_purpose, db)
    db_individuals = await _db_search_individuals(domain, campaign_purpose, db)

    for c in db_companies:
        if campaign_id:
            model = c.get("_model")
            if model and campaign_id not in (model.campaign_ids or []):
                model.campaign_ids = list((model.campaign_ids or [])) + [campaign_id]
        if c["id"] not in seen_company_ids:
            seen_company_ids.add(c["id"])
            companies_out.append(c)

    for i in db_individuals:
        if campaign_id:
            model = i.get("_model")
            if model and campaign_id not in (model.campaign_ids or []):
                model.campaign_ids = list((model.campaign_ids or [])) + [campaign_id]
        if i["id"] not in seen_individual_ids:
            seen_individual_ids.add(i["id"])
            individuals_out.append(i)

    logger.info(f"Phase 1 done ({time.time()-t_start:.1f}s): {len(companies_out)} DB companies, {len(individuals_out)} DB individuals")

    # ═══════════════════════════════════════════════════════════
    #  Phase 2: Company + Individual discovery IN PARALLEL
    # ═══════════════════════════════════════════════════════════
    serper_companies = []
    serper_individuals = []

    if settings.SERPER_API_KEY:
        # Run both Serper+LLM pipelines concurrently
        company_task = _serper_discover_companies(domain, campaign_purpose)
        individual_task = _serper_discover_individuals(domain, campaign_purpose)

        results = await asyncio.gather(company_task, individual_task, return_exceptions=True)

        if isinstance(results[0], Exception):
            logger.error(f"Company discovery failed: {results[0]}")
        else:
            serper_companies = results[0] or []

        if isinstance(results[1], Exception):
            logger.error(f"Individual discovery failed: {results[1]}")
        else:
            serper_individuals = results[1] or []

    logger.info(f"Phase 2 done ({time.time()-t_start:.1f}s): {len(serper_companies)} Serper companies, {len(serper_individuals)} Serper individuals")

    # ── Save companies to DB ──
    for sc in serper_companies:
        saved = await _save_new_company(sc, db, campaign_id=campaign_id)
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

    # ── Save individuals to DB ──
    for si in serper_individuals:
        saved_ind = await _save_new_individual(si, db, campaign_id=campaign_id)
        if saved_ind and saved_ind.id not in seen_individual_ids:
            seen_individual_ids.add(saved_ind.id)
            new_individual_ids.append(saved_ind.id)
            individuals_out.append({
                "id": saved_ind.id,
                "name": saved_ind.name,
                "role": saved_ind.role,
                "email": saved_ind.email,
                "company_id": saved_ind.company_id,
                "company_name": si.get("company_name"),
                "domain_tags": saved_ind.domain_tags or [],
                "known": saved_ind.known,
                "relevance_reason": si.get("relevance_reason"),
                "match_source": "serper_individual",
                "_model": saved_ind,
            })

    await db.commit()
    logger.info(f"Phase 2 saved ({time.time()-t_start:.1f}s): {len(companies_out)} companies, {len(individuals_out)} individuals in DB")

    # ═══════════════════════════════════════════════════════════
    #  Phase 2.5: Link individuals → companies & Hunter email finder
    # ═══════════════════════════════════════════════════════════
    if settings.HUNTER_API_KEY and individuals_out and companies_out:
        logger.info(f"Phase 2.5: Linking individuals to companies & finding emails for {len(individuals_out)} individuals")

        # Build a lookup from company name (lowercase) → company entry
        company_lookup = {}
        for ce in companies_out:
            company_lookup[ce["name"].lower()] = ce
            # Also index by shortened name (e.g. "The Humane Society" → "humane society")
            short = ce["name"].lower().removeprefix("the ").strip()
            if short:
                company_lookup[short] = ce

        # For each individual, try to match to a company and find their email
        async def _find_email_for_individual(ind_entry):
            """Try Hunter email finder for one individual."""
            ind_model = ind_entry.get("_model")
            if not ind_model or ind_model.email:
                return  # Already has email

            # Try to link to a company if not already linked
            if not ind_model.company_id and ind_entry.get("company_name"):
                cn_lower = ind_entry["company_name"].lower()
                matched_company = company_lookup.get(cn_lower)
                # Fuzzy: try partial match
                if not matched_company:
                    for key, ce in company_lookup.items():
                        if cn_lower in key or key in cn_lower:
                            matched_company = ce
                            break
                if matched_company:
                    ind_model.company_id = matched_company["id"]
                    ind_entry["company_id"] = matched_company["id"]
                    ind_entry["company_name"] = matched_company["name"]

            # Now find email via Hunter
            company_id = ind_model.company_id
            # Get the domain either from the linked company model OR from the LLM's company_website
            domain_str = None
            company_model = None
            if company_id:
                for ce in companies_out:
                    if ce["id"] == company_id:
                        company_model = ce.get("_model")
                        break
                if company_model and company_model.website:
                    domain_str = _extract_domain_from_url(company_model.website)
            
            # Fallback to the LLM's extracted company_website if no DB company matched
            if not domain_str and ind_entry.get("company_website"):
                domain_str = _extract_domain_from_url(ind_entry["company_website"])

            if not domain_str:
                # Fallback to Serper email search for independent individuals
                fallback_emails = await _serper_find_email(ind_model.name, ind_model.role or "contact")
                if fallback_emails:
                    ind_model.email = fallback_emails[0]
                    ind_entry["email"] = fallback_emails[0]
                    logger.info(f"  ✅ Found fallback email for {ind_model.name} via web search: {fallback_emails[0]}")
                return

            first_name = ind_model.first_name or (ind_model.name.split()[0] if ind_model.name else "")
            last_name = ind_model.last_name or (" ".join(ind_model.name.split()[1:]) if ind_model.name else "")
            if not first_name or not last_name:
                return

            try:
                result = await hunter_service.find_email(
                    domain=domain_str,
                    first_name=first_name,
                    last_name=last_name,
                )
                if result.get("status") == "ok" and result.get("email"):
                    ind_model.email = result["email"]
                    ind_model.email_confidence = result.get("confidence", 0)
                    ind_model.email_verified = result.get("verified", False)
                    if result.get("position") and not ind_model.role:
                        ind_model.role = result["position"]
                    if result.get("linkedin") and not ind_model.linkedin_url:
                        ind_model.linkedin_url = result["linkedin"]
                    # Update the output dict too
                    ind_entry["email"] = result["email"]
                    logger.info(f"  ✅ Found email for {ind_model.name}: {result['email']}")
                else:
                    logger.info(f"  ❌ No email found for {ind_model.name} at {domain_str} via Hunter")
                    # Fallback to Serper
                    fallback_emails = await _serper_find_email(ind_model.name, domain_str)
                    if fallback_emails:
                        ind_model.email = fallback_emails[0]
                        ind_entry["email"] = fallback_emails[0]
                        logger.info(f"  ✅ Found fallback email for {ind_model.name} via web search: {fallback_emails[0]}")
            except Exception as e:
                logger.error(f"  Hunter email finder error for {ind_model.name}: {e}")

        # Run email finder in parallel batches of 5
        batch_size = 5
        for batch_start in range(0, len(individuals_out), batch_size):
            batch = individuals_out[batch_start:batch_start + batch_size]
            tasks = [_find_email_for_individual(ind) for ind in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

        try:
            await db.commit()
        except Exception:
            await db.rollback()

        found_emails = sum(1 for ind in individuals_out if ind.get("email"))
        logger.info(f"Phase 2.5 done: {found_emails}/{len(individuals_out)} individuals now have emails")

    # ═══════════════════════════════════════════════════════════
    #  Phase 3: Hunter contacts — PARALLEL batches of 5
    # ═══════════════════════════════════════════════════════════
    if settings.HUNTER_API_KEY:
        logger.info(f"Phase 3: Hunter contact discovery for {len(companies_out)} companies")

        # Re-fetch all company models to avoid expired session
        for ce in companies_out:
            model = ce.get("_model")
            if model:
                refreshed = await db.get(Company, model.id)
                if refreshed:
                    ce["_model"] = refreshed

        # Process companies in parallel batches of 5
        batch_size = 5
        companies_to_search = companies_out[:15]
        for batch_start in range(0, len(companies_to_search), batch_size):
            batch = companies_to_search[batch_start:batch_start + batch_size]

            async def _hunt_one(company_entry):
                """Hunter search for a single company (runs in parallel)."""
                company_model = company_entry.get("_model")
                if not company_model:
                    return []
                try:
                    contacts = await _hunter_discover_contacts(
                        company_model, db, seen_individual_ids
                    )
                    return [(company_entry, contact) for contact in contacts]
                except Exception as e:
                    logger.error(f"  Hunter error for '{company_entry.get('name')}': {e}")
                    return []

            batch_tasks = [_hunt_one(ce) for ce in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"  Hunter batch error: {result}")
                    continue
                for company_entry, contact in result:
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

        try:
            await db.commit()
        except Exception:
            await db.rollback()

        logger.info(f"Phase 3 done ({time.time()-t_start:.1f}s): Hunter found contacts")

    # ═══════════════════════════════════════════════════════════
    #  Phase 4: Free email fallback — PARALLEL, top 5 companies
    # ═══════════════════════════════════════════════════════════
    companies_with_contacts = {
        ind.get("company_id") for ind in individuals_out if ind.get("company_id")
    }
    companies_needing_emails = [
        c for c in companies_out if c["id"] not in companies_with_contacts
    ][:5]  # Limit to top 5

    if companies_needing_emails:
        logger.info(f"Phase 4: Free email fallback for {len(companies_needing_emails)} companies")

        async def _free_email_one(company_entry):
            """Free email scraping for one company."""
            try:
                refreshed = await db.get(Company, company_entry["id"])
                if not refreshed:
                    return []
                contacts = await _discover_company_contacts_free(
                    refreshed, db, seen_individual_ids
                )
                return [(company_entry, contact) for contact in contacts]
            except Exception as e:
                logger.error(f"  Free discovery error for '{company_entry.get('name')}': {e}")
                return []

        free_tasks = [_free_email_one(ce) for ce in companies_needing_emails]
        free_results = await asyncio.gather(*free_tasks, return_exceptions=True)

        for result in free_results:
            if isinstance(result, Exception):
                continue
            for company_entry, contact in result:
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
                        "match_source": contact.get("match_source", "website_scrape"),
                        "_model": saved_ind,
                    })

        try:
            await db.commit()
        except Exception:
            await db.rollback()

        logger.info(f"Phase 4 done ({time.time()-t_start:.1f}s)")

    # ═══════════════════════════════════════════════════════════
    #  Phase 5: Resolve company names + build response
    # ═══════════════════════════════════════════════════════════
    company_name_map = {c["id"]: c["name"] for c in companies_out}

    individuals_by_company = {}
    for ind in individuals_out:
        if not ind.get("company_name") and ind.get("company_id"):
            ind["company_name"] = company_name_map.get(ind["company_id"])
            if not ind["company_name"]:
                comp_result = await db.execute(
                    select(Company.name).where(Company.id == ind["company_id"])
                )
                ind["company_name"] = comp_result.scalar_one_or_none()

        cid = ind.get("company_id")
        if cid:
            if cid not in individuals_by_company:
                individuals_by_company[cid] = []
            individuals_by_company[cid].append(ind)

    # Assign best contact to each company
    final_companies = []
    for c in companies_out:
        cid = c["id"]
        contacts = individuals_by_company.get(cid, [])
        if not contacts:
            c["best_contact_id"] = None
            c["best_contact_name"] = None
            c["best_contact_role"] = None
        else:
            best_contact = max(contacts, key=lambda i: _score_role(i.get("role") or ""))
            c["best_contact_id"] = best_contact["id"]
            c["best_contact_name"] = best_contact["name"]
            c["best_contact_role"] = best_contact.get("role") or "Contact"
        final_companies.append(c)

    # Independent individuals (not attached to discovered companies)
    discovered_company_ids = {c["id"] for c in companies_out}
    final_individuals = [i for i in individuals_out if i.get("company_id") not in discovered_company_ids]

    def _clean(entry: dict) -> dict:
        return {k: v for k, v in entry.items() if k != "_model"}

    companies_final = [_clean(c) for c in final_companies[:limit]]
    individuals_final = [_clean(i) for i in final_individuals[:limit]]

    elapsed = time.time() - t_start
    logger.info(f"✅ Discovery complete in {elapsed:.1f}s: {len(companies_final)} companies, {len(individuals_final)} individuals")

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

import httpx
from bs4 import BeautifulSoup

async def _fetch_page_text(url: str) -> str:
    """Fetch and extract visible text from a webpage."""
    try:
        async with httpx.AsyncClient(timeout=4.0, verify=False) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # Kill script and style elements
            for element in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
                element.decompose()
            text = soup.get_text(separator=" ")
            # collapse multiple spaces
            text = " ".join(text.split())
            return text[:12000] # limit to 12k chars to save tokens while capturing most lists
    except Exception as e:
        return ""

def _score_role(role: str) -> int:
    """Score a job title to identify the highest authority contact."""
    if not role:
        return 0
    role = role.lower()
    if any(x in role for x in ["ceo", "chief executive", "founder", "president", "owner"]):
        return 100
    if any(x in role for x in ["cmo", "cto", "coo", "cfo", "chief"]):
        return 90
    if any(x in role for x in ["vp", "vice president", "partner"]):
        return 80
    if any(x in role for x in ["director", "head"]):
        return 70
    if any(x in role for x in ["manager", "lead", "principal"]):
        return 50
    return 10

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
    # Social media
    "linkedin.com", "facebook.com", "twitter.com", "instagram.com",
    "youtube.com", "x.com", "tiktok.com", "pinterest.com", "threads.net",
    # Search / big tech
    "google.com", "bing.com", "yahoo.com", "apple.com",
    # News / media / magazines
    "bloomberg.com", "reuters.com", "techcrunch.com", "forbes.com",
    "medium.com", "substack.com", "wired.com", "theguardian.com",
    "bbc.com", "bbc.co.uk", "cnbc.com", "nytimes.com", "washingtonpost.com",
    "businessinsider.com", "fastcompany.com", "inc.com", "entrepreneur.com",
    "vegconomist.com", "foodnavigator.com", "fooddive.com", "greenqueen.com.hk",
    "plantbasednews.org", "thegrocer.co.uk", "just-food.com",
    # Startup / company directories & databases
    "crunchbase.com", "angel.co", "wellfound.com", "f6s.com",
    "pitchbook.com", "tracxn.com", "dealroom.co", "cbinsights.com",
    "owler.com", "zoominfo.com", "dnb.com", "hoovers.com",
    "craft.co", "growjo.com", "builtwith.com", "stackshare.io",
    "producthunt.com", "g2.com", "capterra.com", "trustpilot.com",
    # Research / academia
    "sciencedirect.com", "tandfonline.com", "springer.com",
    "researchgate.net", "academia.edu", "scholar.google.com",
    "pubmed.ncbi.nlm.nih.gov", "arxiv.org", "ssrn.com",
    # Reference / community
    "wikipedia.org", "reddit.com", "quora.com", "stackexchange.com",
    "stackoverflow.com",
    # E-commerce
    "amazon.com", "amazon.co.uk", "ebay.com", "alibaba.com", "etsy.com",
    # Jobs
    "glassdoor.com", "indeed.com", "lever.co", "greenhouse.io",
    # Reviews / ratings
    "yelp.com", "bbb.org", "bimpactassessment.net",
    # Industry-specific directories / databases
    "gfi.org", "proteinreport.org", "foodhack.global",
    "newfoodmagazine.com", "agfundernews.com", "foodtechconnect.com",
    "thespoon.tech", "ecowatch.com", "treehugger.com",
    "cleantech.com", "greenbiz.com", "sustainablebrands.com",
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
