import asyncio
from app.database.session import AsyncSessionLocal
from app.services.discovery_service import discover_targets
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    async with AsyncSessionLocal() as db:
        print("Running discovery...")
        res = await discover_targets('animal welfare', 'fundraiser', db, 5)
        print("Total Companies:", res['total_companies'])
        print("Total Individuals:", res['total_individuals'])
        for i in res['individuals']:
            print(f" - {i['name']} ({i['email']}) at {i.get('company_name')}")

if __name__ == "__main__":
    asyncio.run(main())
