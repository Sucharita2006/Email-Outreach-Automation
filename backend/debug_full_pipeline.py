"""
Full pipeline diagnostic — traces every step of discover_targets
to find exactly where contacts and individuals are being lost.
"""
import asyncio
import sys
import logging

# Enable verbose logging
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

sys.path.insert(0, ".")

async def main():
    domain = sys.argv[1] if len(sys.argv) > 1 else "animal welfare"
    purpose = sys.argv[2] if len(sys.argv) > 2 else "partnering for animal rescue"

    from app.config import settings
    print("=" * 60)
    print("DIAGNOSTIC: Full Pipeline Trace")
    print("=" * 60)
    print(f"Domain: {domain}")
    print(f"Purpose: {purpose}")
    print(f"HUNTER_API_KEY set: {bool(settings.HUNTER_API_KEY)}")
    print(f"SERPER_API_KEY set: {bool(settings.SERPER_API_KEY)}")
    print(f"OPENROUTER_API_KEY set: {bool(settings.OPENROUTER_API_KEY)}")
    print(f"PRIMARY_MODEL: {settings.OPENROUTER_PRIMARY_MODEL}")
    print()

    # ── Test 1: Serper company discovery ──
    print("=" * 60)
    print("TEST 1: Serper Company Discovery")
    print("=" * 60)
    from app.services.discovery_service import _serper_discover_companies
    companies = await _serper_discover_companies(domain, purpose)
    print(f"Result: {len(companies)} companies found")
    for c in companies[:3]:
        print(f"  - {c.get('name')} | {c.get('website')}")
    print()

    # ── Test 2: Hunter on a real company ──
    print("=" * 60)
    print("TEST 2: Hunter Contact Discovery")
    print("=" * 60)
    from app.services import hunter_service
    if companies:
        test_company = companies[0]
        test_domain = test_company.get("website", "").replace("https://", "").replace("http://", "").split("/")[0]
        print(f"Testing Hunter on: {test_company.get('name')} ({test_domain})")
        
        # Test domain search directly
        result = await hunter_service.domain_search(test_domain, department="management", limit=5)
        print(f"  Hunter status: {result.get('status')}")
        print(f"  Hunter error: {result.get('error')}")
        print(f"  Emails found: {len(result.get('emails', []))}")
        for e in result.get("emails", []):
            print(f"    - {e.get('first_name')} {e.get('last_name')} | {e.get('email')} | {e.get('position')}")
        
        if not result.get("emails"):
            # Try without department filter
            print(f"\n  Retrying without department filter...")
            result2 = await hunter_service.domain_search(test_domain, limit=5)
            print(f"  Hunter status: {result2.get('status')}")
            print(f"  Emails found: {len(result2.get('emails', []))}")
            for e in result2.get("emails", []):
                print(f"    - {e.get('first_name')} {e.get('last_name')} | {e.get('email')} | {e.get('position')}")
    print()

    # ── Test 3: Serper individual discovery ──
    print("=" * 60)
    print("TEST 3: Serper Individual Discovery")
    print("=" * 60)
    from app.services.discovery_service import _serper_discover_individuals
    individuals = await _serper_discover_individuals(domain, purpose)
    print(f"Result: {len(individuals)} individuals found")
    for ind in individuals[:5]:
        print(f"  - {ind.get('name')} | {ind.get('role')} | {ind.get('company_name')}")
    print()

    # ── Test 4: Full discover_targets pipeline ──
    print("=" * 60)
    print("TEST 4: Full discover_targets pipeline")
    print("=" * 60)
    from app.database.session import AsyncSessionLocal
    from app.services.discovery_service import discover_targets

    async with AsyncSessionLocal() as db:
        results = await discover_targets(domain, purpose, db, limit=30)
        print(f"Companies: {results['total_companies']}")
        print(f"Individuals: {results['total_individuals']}")
        print(f"New company IDs: {len(results.get('new_company_ids', []))}")
        print(f"New individual IDs: {len(results.get('new_individual_ids', []))}")
        print()
        
        for c in results["companies"][:5]:
            contact = c.get("best_contact_name", "NONE")
            print(f"  Company: {c['name']} | Contact: {contact} | {c.get('best_contact_role', '')}")
        
        print()
        for i in results["individuals"][:5]:
            print(f"  Individual: {i['name']} | {i.get('role')} | email={i.get('email')}")

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)

asyncio.run(main())
