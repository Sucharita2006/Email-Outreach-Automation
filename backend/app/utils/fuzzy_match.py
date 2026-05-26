"""
Fuzzy Domain Keyword Matching Utility
Uses rapidfuzz to expand domain queries so "vegan" matches "veganism", "plant-based", etc.
Full implementation in Sprint 2.
"""
from rapidfuzz import fuzz, process
from typing import Optional

# Predefined domain taxonomy — expand as needed
DOMAIN_TAXONOMY = [
    "veganism",
    "plant-based",
    "animal-welfare",
    "factory-farming",
    "sustainable-food",
    "food-policy",
    "cruelty-free",
    "alternative-protein",
    "cultivated-meat",
    "vegan-business",
    "food-tech",
    "conscious-capitalism",
    "animal-rights",
    "humane-cosmetics",
    "vegan-fashion",
    "pet-food-reform",
]

# Similarity threshold — tune this (0–100). 70 is a good starting point.
FUZZY_THRESHOLD = 70


def expand_domain_query(query: str, threshold: int = FUZZY_THRESHOLD) -> list[str]:
    """
    Given a user's domain query (e.g., "vegan"), return a list of matching
    domain tags from the taxonomy using fuzzy string matching.

    Example:
        expand_domain_query("vegan")
        → ["veganism", "vegan-business", "veganism", "cruelty-free"]
    """
    query = query.lower().strip()

    # Exact match first
    if query in DOMAIN_TAXONOMY:
        matched = [query]
    else:
        matched = []

    # Fuzzy matches
    results = process.extract(
        query,
        DOMAIN_TAXONOMY,
        scorer=fuzz.partial_ratio,
        limit=10,
    )
    for tag, score, _ in results:
        if score >= threshold and tag not in matched:
            matched.append(tag)

    return matched if matched else [query]  # fallback to raw query if no match
