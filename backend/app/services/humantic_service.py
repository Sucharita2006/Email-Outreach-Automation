"""
Humantic AI Service — Phase 5
Personality profiling for email recipients using DISC + Big Five models.

Provides:
  - Profile creation/fetch by LinkedIn URL
  - DISC type extraction (D/I/S/C)
  - Big Five personality scores
  - Communication preference summary (used as tone_instruction in LLM Call 1)
  - 90-day TTL caching on Individual model

Humantic AI API docs: https://api.humantic.ai
Requires: HUMANTIC_API_KEY in .env
Supports: LinkedIn URL → personality profile
"""

import httpx
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database.models import Individual, DISCType
from app.utils.cache_manager import is_cache_fresh
from app.utils.rate_limiter import RateLimiter

# Humantic: 3 concurrent max (free tier is limited)
_humantic_limiter = RateLimiter(concurrency=3, calls_per_second=1.0)

# 90-day TTL (personality doesn't change quickly)
_TTL = settings.HUMANTIC_CACHE_TTL_SECONDS


# ════════════════════════════════════════════════════════════
#  DISC Interpretation Tables
# ════════════════════════════════════════════════════════════

_DISC_TONE_INSTRUCTIONS = {
    DISCType.D: (
        "Be direct, concise, and results-focused. Lead with the value proposition immediately. "
        "Skip pleasantries. Use confident, action-oriented language. No fluff. Under 150 words."
    ),
    DISCType.I: (
        "Be warm, enthusiastic, and vision-oriented. Use energetic language and express excitement "
        "about the partnership. Brief storytelling is welcome. Keep it conversational and upbeat."
    ),
    DISCType.S: (
        "Be warm, reassuring, and relationship-focused. Emphasize trust, collaboration, and shared "
        "values. Avoid pressure. Focus on how the partnership benefits both sides and their teams."
    ),
    DISCType.C: (
        "Be precise, logical, and evidence-based. Include specific facts, data points, or verifiable "
        "claims. Avoid vague statements. The recipient values accuracy over enthusiasm."
    ),
    DISCType.UNKNOWN: (
        "Use a professional, neutral tone that balances warmth and clarity. "
        "Be specific and concise. Avoid generic openers."
    ),
}

_DISC_AVOID = {
    DISCType.D: "Avoid lengthy introductions, vague language, or over-explaining. Don't waste their time.",
    DISCType.I: "Avoid dry, overly formal language or excessive detail. Keep the energy up.",
    DISCType.S: "Avoid high-pressure language, ultimatums, or moving too fast. Don't be pushy.",
    DISCType.C: "Avoid superlatives, unsupported claims, or emotional appeals without evidence.",
    DISCType.UNKNOWN: "Avoid clichés and overly promotional language.",
}

_DISC_LABELS = {
    "D": DISCType.D,
    "I": DISCType.I,
    "S": DISCType.S,
    "C": DISCType.C,
    "Di": DISCType.D, "DC": DISCType.D,
    "Id": DISCType.I, "Is": DISCType.I,
    "Si": DISCType.S, "Sc": DISCType.S,
    "Cs": DISCType.C, "Cd": DISCType.C,
}


def _parse_disc_type(raw: Optional[str]) -> DISCType:
    """Parse a raw DISC string from Humantic API into our DISCType enum."""
    if not raw:
        return DISCType.UNKNOWN
    cleaned = raw.strip()
    # Try exact match first, then first character
    return _DISC_LABELS.get(cleaned) or _DISC_LABELS.get(cleaned[0].upper(), DISCType.UNKNOWN)


def _parse_big5(personality_data: dict) -> dict:
    """
    Extract Big Five scores from Humantic API response.
    Returns a normalized dict with scores 0.0–1.0.
    """
    big5_map = {
        "openness": ["openness", "open_to_experience"],
        "conscientiousness": ["conscientiousness"],
        "extraversion": ["extraversion", "extroversion"],
        "agreeableness": ["agreeableness"],
        "neuroticism": ["neuroticism", "emotional_stability"],
    }
    result = {}
    for trait, keys in big5_map.items():
        for key in keys:
            val = personality_data.get(key)
            if val is not None:
                # Humantic returns 0–100 or 0.0–1.0 depending on version
                result[trait] = round(float(val) / 100, 3) if float(val) > 1 else round(float(val), 3)
                break
    return result


def _build_communication_pref(disc: DISCType, big5: dict, raw_data: dict) -> str:
    """
    Build a human-readable communication preference summary combining
    DISC style, Big Five traits, and any Humantic-provided insights.
    This becomes the tone_instruction field in LLM Call 1.
    """
    lines = [f"DISC type: {disc.value}"]
    lines.append(_DISC_TONE_INSTRUCTIONS[disc])

    if big5:
        high = [k for k, v in big5.items() if v and v > 0.65]
        low = [k for k, v in big5.items() if v and v < 0.35]
        if high:
            lines.append(f"High: {', '.join(high)} — lean into these traits in your writing.")
        if low:
            lines.append(f"Low: {', '.join(low)} — avoid assuming these preferences.")

    # Humantic sometimes provides a plain-text summary
    persona_summary = raw_data.get("persona_summary") or raw_data.get("summary")
    if persona_summary:
        lines.append(f"Humantic insight: {persona_summary[:200]}")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
#  Core API Calls
# ════════════════════════════════════════════════════════════

async def create_profile(linkedin_url: str) -> dict:
    """
    Create (or retrieve) a Humantic AI personality profile from a LinkedIn URL.

    Humantic API: POST /user-persona/
    Body: {"id": "<linkedin_url>", "persona": ["sales"]}

    Returns raw API response dict.
    """
    if not settings.HUMANTIC_API_KEY:
        return {"status": "no_api_key"}

    url = f"{settings.HUMANTIC_BASE_URL}/user-persona/"
    payload = {
        "id": linkedin_url,
        "persona": ["sales"],   # Sales persona gives communication-focused insights
    }
    params = {"apikey": settings.HUMANTIC_API_KEY}

    async with _humantic_limiter:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(url, json=payload, params=params)
                resp.raise_for_status()
                return {"status": "ok", "data": resp.json()}
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    return {"status": "rate_limited", "error": "Humantic rate limit exceeded."}
                if e.response.status_code == 404:
                    return {"status": "not_found", "error": "LinkedIn profile not found in Humantic."}
                return {
                    "status": "error",
                    "error": f"Humantic {e.response.status_code}: {e.response.text[:200]}",
                }
            except httpx.RequestError as e:
                return {"status": "error", "error": str(e)}


async def fetch_profile(linkedin_url: str) -> dict:
    """
    Fetch an existing Humantic AI profile (must have been created first).

    Humantic API: GET /user-persona/?apikey=...&id=<linkedin_url>
    """
    if not settings.HUMANTIC_API_KEY:
        return {"status": "no_api_key"}

    url = f"{settings.HUMANTIC_BASE_URL}/user-persona/"
    params = {
        "apikey": settings.HUMANTIC_API_KEY,
        "id": linkedin_url,
    }

    async with _humantic_limiter:
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return {"status": "ok", "data": resp.json()}
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return {"status": "not_found"}
                return {
                    "status": "error",
                    "error": f"Humantic {e.response.status_code}: {e.response.text[:200]}",
                }
            except httpx.RequestError as e:
                return {"status": "error", "error": str(e)}


def _extract_personality(api_response: dict) -> dict:
    """
    Parse Humantic API response into our internal personality schema.

    Humantic response structure (v1):
      results.personality.disc_profile  → {"type": "D", ...}
      results.personality.big5          → {"openness": 0.8, ...}
      results.persona_summary            → "This person is..."
    """
    results = api_response.get("data", {}).get("results", {})
    personality = results.get("personality", {})

    # DISC
    disc_profile = personality.get("disc_profile", {})
    raw_disc = disc_profile.get("type") or disc_profile.get("personality_type")
    disc = _parse_disc_type(raw_disc)

    # Big Five
    big5_raw = personality.get("big5", {}) or personality.get("ocean", {})
    big5 = _parse_big5(big5_raw)

    # Communication preference summary
    comm_pref = _build_communication_pref(disc, big5, results)

    return {
        "disc_type": disc,
        "big5": big5,
        "communication_pref": comm_pref,
        "raw_disc": raw_disc,
        "persona_summary": results.get("persona_summary") or results.get("summary"),
    }


# ════════════════════════════════════════════════════════════
#  Individual Enrichment (main entry point)
# ════════════════════════════════════════════════════════════

async def enrich_individual(
    individual: Individual,
    db: AsyncSession,
    force_refresh: bool = False,
) -> dict:
    """
    Enrich an individual's personality profile from Humantic AI.
    Requires: individual.linkedin_url to be set.
    Respects 90-day TTL cache.

    Updates:
      - individual.humantic_disc
      - individual.humantic_big5
      - individual.humantic_communication_pref
      - individual.humantic_cached_at
    """
    # ── Check cache ───────────────────────────────────────────
    if not force_refresh and is_cache_fresh(individual.humantic_cached_at, _TTL):
        return {
            "status": "cached",
            "individual_id": individual.id,
            "name": individual.name,
            "cached_at": individual.humantic_cached_at.isoformat(),
            "disc_type": individual.humantic_disc.value if individual.humantic_disc else "UNKNOWN",
            "communication_pref": individual.humantic_communication_pref,
        }

    # ── Require LinkedIn URL ──────────────────────────────────
    if not individual.linkedin_url:
        return {
            "status": "no_linkedin",
            "individual_id": individual.id,
            "name": individual.name,
            "message": "LinkedIn URL required for Humantic AI profiling.",
            # Fallback: use UNKNOWN DISC type with neutral instructions
            "disc_type": DISCType.UNKNOWN.value,
            "communication_pref": _DISC_TONE_INSTRUCTIONS[DISCType.UNKNOWN],
            "tone_instruction": _DISC_TONE_INSTRUCTIONS[DISCType.UNKNOWN],
            "avoid": _DISC_AVOID[DISCType.UNKNOWN],
        }

    # ── Try fetch first, then create if not found ─────────────
    api_result = await fetch_profile(individual.linkedin_url)

    if api_result.get("status") == "not_found":
        # Profile doesn't exist yet — create it (Humantic will process async)
        api_result = await create_profile(individual.linkedin_url)
        if api_result.get("status") not in ("ok",):
            return {
                "status": api_result.get("status", "error"),
                "individual_id": individual.id,
                "name": individual.name,
                "error": api_result.get("error"),
            }

    if api_result.get("status") != "ok":
        return {
            "status": api_result.get("status"),
            "individual_id": individual.id,
            "error": api_result.get("error"),
        }

    # ── Parse + store ─────────────────────────────────────────
    personality = _extract_personality(api_result)
    now = datetime.now(timezone.utc)

    individual.humantic_disc = personality["disc_type"]
    individual.humantic_big5 = personality["big5"]
    individual.humantic_communication_pref = personality["communication_pref"]
    individual.humantic_cached_at = now

    await db.flush()

    disc = personality["disc_type"]
    return {
        "status": "enriched",
        "individual_id": individual.id,
        "name": individual.name,
        "disc_type": disc.value,
        "raw_disc": personality.get("raw_disc"),
        "big5": personality["big5"],
        "communication_pref": personality["communication_pref"],
        "tone_instruction": _DISC_TONE_INSTRUCTIONS[disc],
        "avoid": _DISC_AVOID[disc],
        "persona_summary": personality.get("persona_summary"),
    }


# ════════════════════════════════════════════════════════════
#  Fallback — No LinkedIn, No API Key
# ════════════════════════════════════════════════════════════

def get_fallback_personality(individual: Individual) -> dict:
    """
    Return a usable (but generic) personality profile when Humantic data
    is unavailable. Used by LLM Call 1 so it can still run without Humantic.
    """
    disc = individual.humantic_disc or DISCType.UNKNOWN
    return {
        "disc_type": disc.value,
        "communication_pref": individual.humantic_communication_pref or _DISC_TONE_INSTRUCTIONS[disc],
        "tone_instruction": _DISC_TONE_INSTRUCTIONS[disc],
        "avoid": _DISC_AVOID[disc],
        "is_fallback": disc == DISCType.UNKNOWN,
    }


def get_disc_instructions(disc_type: DISCType) -> dict:
    """Return tone and avoid instructions for a given DISC type."""
    return {
        "disc_type": disc_type.value,
        "tone_instruction": _DISC_TONE_INSTRUCTIONS[disc_type],
        "avoid": _DISC_AVOID[disc_type],
    }


# ════════════════════════════════════════════════════════════
#  Batch Enrichment
# ════════════════════════════════════════════════════════════

async def batch_enrich_individuals(
    individual_ids: list[str],
    db: AsyncSession,
    force_refresh: bool = False,
) -> list[dict]:
    """
    Enrich multiple individuals from Humantic AI.
    Processes sequentially (Humantic free tier is strict on rate limits).
    """
    import asyncio

    stmt = select(Individual).where(Individual.id.in_(individual_ids))
    result = await db.execute(stmt)
    individuals = result.scalars().all()

    results = []
    for ind in individuals:
        r = await enrich_individual(ind, db, force_refresh=force_refresh)
        results.append(r)
        await asyncio.sleep(0.5)  # Be polite to Humantic API

    await db.commit()
    return results
