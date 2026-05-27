"""Debug script to trace the discovery pipeline step by step."""
import asyncio
from app.services import serper_service
from app.services.llm_service import call_llm_json

async def test():
    domain = "Environmental Education"
    campaign_purpose = "Impact Entrepreneurship, Community Building"

    # Step 1: Test Serper
    print("=" * 60)
    print("STEP 1: Serper Web Search")
    print("=" * 60)
    queries = [
        f"{domain} companies OR startups OR organizations",
        f"{domain} Impact Entrepreneurship companies",
    ]
    all_results = []
    for q in queries:
        print(f"\nQuery: {q}")
        result = await serper_service.web_search(q, num=10)
        print(f"  Status: {result.get('status')}")
        print(f"  Error: {result.get('error')}")
        organic = result.get("organic", [])
        print(f"  Organic results: {len(organic)}")
        for item in organic[:3]:
            print(f"    Title: {item.get('title', '')[:80]}")
            print(f"    Link: {item.get('link', '')[:80]}")
            print(f"    Snippet: {item.get('snippet', '')[:100]}")
            print()
        if result.get("status") == "ok":
            all_results.extend(organic)

    if not all_results:
        print("\nSERPER RETURNED NO RESULTS. Pipeline stops here.")
        return

    # Step 2: Build LLM prompt
    print("=" * 60)
    print("STEP 2: LLM Parsing")
    print("=" * 60)
    snippets = []
    for r in all_results:
        snippets.append(f"Title: {r.get('title')}\nLink: {r.get('link')}\nSnippet: {r.get('snippet')}\n")
    snippets_text = "\n".join(snippets)

    prompt = f"""
We are looking for companies in the domain "{domain}" for a campaign with this purpose: "{campaign_purpose}".
Here are raw Google search results:

{snippets_text}

Analyze these results and extract ONLY the actual, real companies that fit the domain and campaign.
IGNORE articles, guides, directories (like crunchbase/linkedin), blogs, and "How to" pages.

For each company found, provide:
- name: The actual company name
- website: Their website URL (extracted from the link)
- sector: A 1-3 word sector (e.g. Food Tech, Alternative Dairy)
- product_type: What they actually make or do (e.g. Fermented proteins, Plant-based milk)
- relevance_reason: A 1-2 sentence explanation of exactly how this company fits our domain and campaign purpose.

Output JSON only in this exact structure:
{{
  "companies": [
    {{
      "name": "...",
      "website": "...",
      "sector": "...",
      "product_type": "...",
      "relevance_reason": "..."
    }}
  ]
}}
"""

    llm_res = await call_llm_json(
        prompt=prompt,
        system_prompt="You are an expert business researcher. Output strictly valid JSON.",
        required_keys=["companies"]
    )

    print(f"  LLM Status: {llm_res['status']}")
    print(f"  LLM Model: {llm_res.get('model')}")
    print(f"  LLM Error: {llm_res.get('error')}")
    print(f"  LLM Raw (first 500 chars): {llm_res.get('raw', '')[:500]}")

    if llm_res["status"] == "ok":
        companies = llm_res["data"].get("companies", [])
        print(f"\n  Companies extracted: {len(companies)}")
        for c in companies[:5]:
            print(f"    Name: {c.get('name')}")
            print(f"    Website: {c.get('website')}")
            print(f"    Sector: {c.get('sector')}")
            print(f"    Product: {c.get('product_type')}")
            print(f"    Reason: {c.get('relevance_reason', '')[:100]}")
            print()

asyncio.run(test())
