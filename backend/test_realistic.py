import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        r = await client.get("/emails/campaigns")
        campaigns = r.json()
        if not campaigns:
            print("No campaigns!")
            return
        campaign = campaigns[0]
        
        # We know from the screenshot that "Melanie Joy", "Priya Sawhney", "ASPCA", and "The Humane Society" were selected.
        # But since DB is cleared, let's use the actual targets currently in the DB.
        
        r = await client.get(f"/targets/companies?campaign_id={campaign['id']}")
        companies = r.json()
        
        r = await client.get(f"/targets/individuals?campaign_id={campaign['id']}")
        individuals = r.json()
        
        print("Got companies:", len(companies))
        print("Got individuals:", len(individuals))
        
        targets = []
        # Add 2 individuals
        for ind in individuals[:2]:
            targets.append({"individual_id": ind["id"], "company_id": ind.get("company_id")})
        
        # Add 2 companies (without individuals)
        for comp in companies[:2]:
            targets.append({"individual_id": None, "company_id": comp["id"]})
            
        print("Sending targets:", targets)
        
        r = await client.post("/emails/generate/campaign-targets", json={
            "campaign_id": campaign["id"],
            "targets": targets,
            "force_refresh_analysis": False,
        }, timeout=120)
        
        print(f"Status: {r.status_code}")
        print(f"Response: {r.json()}")

if __name__ == "__main__":
    asyncio.run(test())
