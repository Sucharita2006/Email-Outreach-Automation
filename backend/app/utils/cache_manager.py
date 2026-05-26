"""
Cache Manager — TTL-based cache validation for all external API responses.
Checks whether a cached result is still fresh based on its timestamp and TTL.
"""
from datetime import datetime, timezone
from typing import Optional


def is_cache_fresh(cached_at: Optional[datetime], ttl_seconds: int) -> bool:
    """
    Returns True if the cached result is still within its TTL window.

    Args:
        cached_at: The datetime when the cache was last populated.
        ttl_seconds: How long (in seconds) the cache is considered valid.

    Returns:
        True if cache is fresh, False if stale or missing.

    TTL Reference:
        Hunter domain search   → 14 days  (1,209,600s)
        Serper news/web        → 7 days   (604,800s)
        OpenCorporates         → 30 days  (2,592,000s)
        Humantic AI profile    → 90 days  (7,776,000s)
        Individual LLM analysis → 30 days (2,592,000s)
        Company LLM analysis   → 7 days  (604,800s)
    """
    if cached_at is None:
        return False

    # Make timezone-aware if naive
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age_seconds = (now - cached_at).total_seconds()
    return age_seconds < ttl_seconds


def cache_age_hours(cached_at: Optional[datetime]) -> Optional[float]:
    """Returns how many hours ago the cache was populated, or None if never cached."""
    if cached_at is None:
        return None
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
