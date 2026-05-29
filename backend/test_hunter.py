"""Quick Hunter test"""
import asyncio, sys
sys.path.insert(0, ".")

async def main():
    from app.services import hunter_service
    from app.config import settings
    
    print(f"HUNTER_API_KEY set: {bool(settings.HUNTER_API_KEY)}")
    print(f"HUNTER_API_KEY value (first 10): {settings.HUNTER_API_KEY[:10]}...")
    
    # Test 1: Direct Hunter domain search
    print("\n--- Test: rover.com ---")
    r = await hunter_service.domain_search("rover.com", limit=3)
    print(f"Status: {r.get('status')}")
    print(f"Error: {r.get('error')}")
    print(f"Total: {r.get('total')}")
    for e in r.get("emails", []):
        print(f"  {e['first_name']} {e['last_name']} | {e['email']} | {e.get('position')}")

    # Test 2: thefarmersdog.com
    print("\n--- Test: thefarmersdog.com ---")
    r2 = await hunter_service.domain_search("thefarmersdog.com", limit=3)
    print(f"Status: {r2.get('status')}")
    print(f"Error: {r2.get('error')}")
    print(f"Total: {r2.get('total')}")
    for e in r2.get("emails", []):
        print(f"  {e['first_name']} {e['last_name']} | {e['email']} | {e.get('position')}")

asyncio.run(main())
