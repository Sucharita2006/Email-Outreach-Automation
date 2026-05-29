import httpx, json

r = httpx.post(
    'http://localhost:8000/targets/discover',
    json={
        'campaign_name': 'test',
        'domain': 'plant based',
        'campaign_purpose': 'outreach',
        'limit': 5,
    },
    timeout=120,
)
d = r.json()
print(f"Status: {r.status_code}")
print(f"Companies: {d.get('total_companies', 0)}")
print(f"Individuals: {d.get('total_individuals', 0)}")
for c in d.get('companies', []):
    print(f"  {c['name']} | contact: {c.get('best_contact_name', 'NONE')} | {c.get('best_contact_role', '')}")
