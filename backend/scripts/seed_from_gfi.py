"""
Seed script stub for Sprint 1b — GFI CSV import.
Full implementation in Sprint 1b.
Run: python backend/scripts/seed_from_gfi.py
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def seed_from_gfi(csv_path: str = "data/gfi_companies.csv"):
    """
    Import companies from GFI Alternative Protein Company Database CSV.
    Full implementation in Sprint 1b.
    """
    print(f"[Sprint 1b] GFI seed script — will import from {csv_path}")
    print("Full implementation coming in Sprint 1b.")


async def seed_from_json(json_path: str = None):
    # Resolve path relative to project root (one level up from backend/)
    if json_path is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        json_path = os.path.join(project_root, "data", "seed_data.json")
    """
    Import sample seed data for testing. Run this now to populate the DB.
    """
    from app.database.session import init_db, AsyncSessionLocal
    from app.database.models import Company, Individual

    print(f"[Seed] Loading sample data from {json_path}...")
    await init_db()

    with open(json_path, "r") as f:
        data = json.load(f)

    async with AsyncSessionLocal() as session:
        # Seed companies
        for c in data.get("companies", []):
            company = Company(
                name=c["name"],
                website=c.get("website"),
                linkedin_url=c.get("linkedin_url"),
                description=c.get("description"),
                industry=c.get("industry"),
                sector=c.get("sector"),
                product_type=c.get("product_type"),
                size=c.get("size"),
                domain_tags=c.get("domain_tags", []),
                source=c.get("source", "seed_data"),
            )
            session.add(company)

        await session.commit()
        print(f"[Seed] OK - Inserted {len(data.get('companies', []))} companies.")
        print("[Seed] DONE - Sample data seeded successfully.")


if __name__ == "__main__":
    asyncio.run(seed_from_json())
