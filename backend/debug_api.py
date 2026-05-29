"""Reproduce the HTTP 500 from the API endpoint itself."""
import asyncio
import traceback
import httpx

async def test():
    # First, get campaigns
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Get campaigns  
        r = await client.get("/emails/campaigns")
        campaigns = r.json()
        print(f"Campaigns: {len(campaigns)}")
        if not campaigns:
            print("No campaigns!")
            return
        
        campaign = campaigns[0]
        print(f"Campaign: {campaign['name']} (id={campaign['id']})")
        
        # Get companies
        r = await client.get(f"/targets/companies?campaign_id={campaign['id']}&limit=5")
        companies = r.json()
        print(f"Companies: {len(companies)}")
        
        # Get individuals
        r = await client.get(f"/targets/individuals?campaign_id={campaign['id']}&limit=5")
        individuals = r.json()
        print(f"Individuals: {len(individuals)}")
        
        if not companies and not individuals:
            print("No targets!")
            return
        
        # Build targets - pick first company (no individual)
        targets = []
        if companies:
            targets.append({"individual_id": None, "company_id": companies[0]["id"]})
        if individuals:
            targets.append({"individual_id": individuals[0]["id"], "company_id": individuals[0].get("company_id")})
        
        print(f"\nSending targets: {targets}")
        
        # Generate
        r = await client.post("/emails/generate/campaign-targets", json={
            "campaign_id": campaign["id"],
            "targets": targets,
            "force_refresh_analysis": False,
        }, timeout=120)
        
        print(f"\nStatus: {r.status_code}")
        print(f"Response: {r.text[:2000]}")

if __name__ == "__main__":
    asyncio.run(test())
