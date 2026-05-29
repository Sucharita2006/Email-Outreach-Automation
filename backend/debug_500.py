"""Reproduce the HTTP 500 from generate_email_for_target."""
import asyncio
import traceback
from app.database.session import AsyncSessionLocal
from app.database.models import Company, Individual
from app.services.research_orchestrator import generate_email_for_target

async def test():
    async with AsyncSessionLocal() as db:
        # Get first company and individual
        from sqlalchemy import select
        
        companies = (await db.execute(select(Company).limit(1))).scalars().all()
        individuals = (await db.execute(select(Individual).limit(1))).scalars().all()
        
        if not companies:
            print("No companies in DB!")
            return
        if not individuals:
            print("No individuals in DB!")
            return
        
        company = companies[0]
        individual = individuals[0]
        
        print(f"Company: {company.name} (id={company.id})")
        print(f"Individual: {individual.name} (id={individual.id})")
        print(f"Individual company_id: {individual.company_id}")
        
        # Try to access individual.company (lazy load in async = error?)
        try:
            print(f"individual.company = {individual.company}")
        except Exception as e:
            print(f"ERROR accessing individual.company: {e}")

        # Get a campaign
        from app.database.models import OutreachCampaign
        campaigns = (await db.execute(select(OutreachCampaign).limit(1))).scalars().all()
        if not campaigns:
            print("No campaigns!")
            return
        campaign = campaigns[0]
        print(f"Campaign: {campaign.name} (id={campaign.id})")

        # Now try generate
        try:
            result = await generate_email_for_target(
                individual=individual,
                company=company,
                campaign_id=campaign.id,
                db=db,
            )
            print(f"Result: {result}")
        except Exception as e:
            print(f"FULL ERROR:\n{traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(test())
