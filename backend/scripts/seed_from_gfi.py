"""
Seed Script — GFI Alternative Protein Database + JSON Sample Data
================================================================
Usage:
  # Seed from the bundled JSON sample data (20 companies + 5 individuals):
  python backend/scripts/seed_from_gfi.py

  # Seed from a GFI CSV file:
  python backend/scripts/seed_from_gfi.py --csv data/gfi_companies.csv

  # Reset DB and re-seed:
  python backend/scripts/seed_from_gfi.py --clear

  # Download GFI CSV:
  https://gfi.org/resource/alternative-protein-company-database/

CSV Column Mapping (GFI Alternative Protein Company Database):
  Company Name → name
  Website      → website
  Sector       → sector  (Consumer Brand / Ingredient Supplier / Manufacturer)
  Product Type → product_type
  Country      → metadata.country
  Description  → description
  Funding      → metadata.funding_stage
"""

import asyncio
import csv
import json
import argparse
import os
import sys
from pathlib import Path

# ── Path setup: allow running from project root or backend/ ─
_script_dir = Path(__file__).resolve().parent
_backend_dir = _script_dir.parent
_project_root = _backend_dir.parent
sys.path.insert(0, str(_backend_dir))

# ── Rich for pretty terminal output ──────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import track
    import sys
    console = Console(force_terminal=True, force_jupyter=False, file=open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))
    def log(msg, style=""):
        try:
            console.print(msg, style=style)
        except Exception:
            print(msg.replace('[bold]','').replace('[/bold]','').replace('[bold green]','').replace('[/bold green]','').replace('[bold red]','').replace('[/bold red]','').replace('[cyan]','').replace('[/cyan]','').replace('[yellow]','').replace('[/yellow]','').replace('[dim]','').replace('[/dim]',''))
except ImportError:
    def log(msg, style=""):
        print(msg)
    def track(items, description=""):
        return items


# ════════════════════════════════════════════════════════════
#  Domain tag mapping for GFI product_types
# ════════════════════════════════════════════════════════════

DOMAIN_TAG_MAP = {
    "plant-based meat":         ["plant-based", "alternative-protein", "veganism", "sustainable-food"],
    "plant-based dairy":        ["plant-based", "alternative-dairy", "veganism", "sustainable-food"],
    "plant-based egg":          ["plant-based", "alternative-protein", "veganism"],
    "plant-based seafood":      ["plant-based", "alternative-seafood", "veganism", "sustainable-food"],
    "cultivated meat":          ["cultivated-meat", "alternative-protein", "animal-welfare", "food-tech"],
    "cultivated seafood":       ["cultivated-meat", "alternative-seafood", "animal-welfare", "food-tech"],
    "fermentation-derived protein": ["fermentation", "alternative-protein", "food-tech", "sustainable-food"],
    "precision fermentation":   ["precision-fermentation", "alternative-protein", "food-tech", "animal-welfare"],
    "mycelium protein":         ["fermentation", "alternative-protein", "food-tech", "veganism"],
}

GFI_SECTOR_MAP = {
    "Consumer Brand":       "consumer brand",
    "Ingredient Supplier":  "ingredient supplier",
    "Manufacturer":         "manufacturer",
    "Technology Platform":  "technology platform",
    "Research":             "research",
    "Cultivated":           "cultivated meat",
    "Fermentation":         "fermentation",
    "Precision Fermentation": "precision fermentation",
}


def _get_domain_tags(product_type: str, sector: str = "") -> list[str]:
    """Map GFI product_type to internal domain_tags list."""
    if not product_type:
        return ["alternative-protein"]
    pt_lower = product_type.lower().strip()
    for key, tags in DOMAIN_TAG_MAP.items():
        if key in pt_lower:
            return tags
    # Fallback
    return ["alternative-protein", "sustainable-food"]


# ════════════════════════════════════════════════════════════
#  Core seed functions
# ════════════════════════════════════════════════════════════

async def seed_from_json(json_path: str = None, clear: bool = False) -> dict:
    """
    Seed the database from the bundled seed_data.json file.
    Handles duplicate detection — won't insert the same company name twice.

    Returns: {companies_inserted, individuals_inserted, companies_skipped}
    """
    if json_path is None:
        json_path = str(_project_root / "data" / "seed_data.json")

    log(f"\n[bold green]📂 Loading seed data from:[/bold green] {json_path}")

    from app.database.session import init_db, AsyncSessionLocal
    from app.database.models import Company, Individual
    from sqlalchemy import select

    await init_db()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    companies_data = [c for c in data.get("companies", []) if not c.get("_comment")]
    individuals_data = data.get("individuals", [])

    stats = {"companies_inserted": 0, "companies_skipped": 0, "individuals_inserted": 0, "individuals_skipped": 0}

    async with AsyncSessionLocal() as session:
        # ── Clear if requested ────────────────────────────────
        if clear:
            from app.database.models import OutreachEmail, Individual as Ind
            for model in [OutreachEmail, Ind, Company]:
                result = await session.execute(select(model))
                for row in result.scalars().all():
                    await session.delete(row)
            await session.commit()
            log("[yellow]⚠️  Database cleared.[/yellow]")

        # ── Load existing company names ───────────────────────
        existing_result = await session.execute(select(Company.name))
        existing_names = {row[0].lower() for row in existing_result.all()}

        # ── Seed companies ────────────────────────────────────
        company_id_map = {}  # name → id (for individual linking)

        for c in track(companies_data, description="Seeding companies..."):
            name = c.get("name", "").strip()
            if not name:
                continue

            if name.lower() in existing_names:
                stats["companies_skipped"] += 1
                # Still need the ID for individuals
                id_result = await session.execute(select(Company).where(Company.name == name))
                existing = id_result.scalar_one_or_none()
                if existing:
                    company_id_map[name] = existing.id
                continue

            company = Company(
                name=name,
                website=c.get("website"),
                linkedin_url=c.get("linkedin_url"),
                description=c.get("description"),
                industry=c.get("industry"),
                sector=c.get("sector"),
                product_type=c.get("product_type"),
                size=c.get("size"),
                domain_tags=c.get("domain_tags") or _get_domain_tags(c.get("product_type", ""), c.get("sector", "")),
                source=c.get("source", "seed_data"),
                metadata=c.get("metadata"),
            )
            session.add(company)
            await session.flush()  # get ID
            company_id_map[name] = company.id
            existing_names.add(name.lower())
            stats["companies_inserted"] += 1

        await session.commit()

        # ── Seed individuals ──────────────────────────────────
        ind_result = await session.execute(select(Individual.email))
        existing_emails = {row[0].lower() for row in ind_result.all() if row[0]}

        for ind in track(individuals_data, description="Seeding individuals..."):
            email = (ind.get("email") or "").strip().lower()
            name = ind.get("name", "").strip()

            if email and email in existing_emails:
                stats["individuals_skipped"] += 1
                continue

            # Link to company
            company_name = ind.get("company_name", "").strip()
            company_id = company_id_map.get(company_name)
            if not company_id and company_name:
                cid_result = await session.execute(select(Company).where(Company.name == company_name))
                comp = cid_result.scalar_one_or_none()
                if comp:
                    company_id = comp.id

            individual = Individual(
                company_id=company_id,
                name=name,
                role=ind.get("role"),
                email=email or None,
                email_verified=ind.get("email_verified", False),
                linkedin_url=ind.get("linkedin_url"),
                domain_tags=ind.get("domain_tags") or ["alternative-protein"],
                source=ind.get("source", "seed_data"),
            )
            session.add(individual)
            if email:
                existing_emails.add(email)
            stats["individuals_inserted"] += 1

        await session.commit()

    return stats


async def seed_from_gfi_csv(csv_path: str, clear: bool = False) -> dict:
    """
    Seed from a GFI Alternative Protein Company Database CSV export.
    Download from: https://gfi.org/resource/alternative-protein-company-database/

    Expected GFI CSV columns (may vary by export year):
      Company Name, Website, Sector, Product Type, Country, Description, ...
    """
    log(f"\n[bold green]📊 Loading GFI CSV:[/bold green] {csv_path}")

    if not os.path.exists(csv_path):
        log(f"[bold red]❌ File not found:[/bold red] {csv_path}", "red")
        log("Download the GFI database from: https://gfi.org/resource/alternative-protein-company-database/")
        return {"error": "CSV file not found"}

    from app.database.session import init_db, AsyncSessionLocal
    from app.database.models import Company
    from sqlalchemy import select

    await init_db()

    # Parse CSV
    companies_to_insert = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]
        log(f"[dim]CSV columns: {', '.join(headers)}[/dim]")

        # Map common GFI column variations
        col_map = {
            "name": next((h for h in reader.fieldnames or [] if "company" in h.lower() and "name" in h.lower()), "Company Name"),
            "website": next((h for h in reader.fieldnames or [] if "website" in h.lower() or "url" in h.lower()), "Website"),
            "sector": next((h for h in reader.fieldnames or [] if "sector" in h.lower()), "Sector"),
            "product_type": next((h for h in reader.fieldnames or [] if "product" in h.lower()), "Product Type"),
            "country": next((h for h in reader.fieldnames or [] if "country" in h.lower()), "Country"),
            "description": next((h for h in reader.fieldnames or [] if "description" in h.lower() or "about" in h.lower()), "Description"),
        }

        for row in reader:
            name = row.get(col_map["name"], "").strip()
            if not name or name.lower() in ("company name", "name"):
                continue

            product_type = row.get(col_map["product_type"], "").strip()
            sector = row.get(col_map["sector"], "").strip()
            country = row.get(col_map["country"], "").strip()

            companies_to_insert.append({
                "name": name,
                "website": row.get(col_map["website"], "").strip() or None,
                "sector": GFI_SECTOR_MAP.get(sector, sector.lower() if sector else None),
                "product_type": product_type.lower() if product_type else None,
                "description": row.get(col_map["description"], "").strip() or None,
                "domain_tags": _get_domain_tags(product_type, sector),
                "source": "gfi_csv",
                "metadata": {"country": country} if country else None,
            })

    log(f"[cyan]Found {len(companies_to_insert)} companies in CSV[/cyan]")

    stats = {"companies_inserted": 0, "companies_skipped": 0, "individuals_inserted": 0}

    async with AsyncSessionLocal() as session:
        if clear:
            from app.database.models import OutreachEmail, Individual
            for model in [OutreachEmail, Individual, Company]:
                result = await session.execute(select(model))
                for row in result.scalars().all():
                    await session.delete(row)
            await session.commit()
            log("[yellow]⚠️  Database cleared.[/yellow]")

        existing_result = await session.execute(select(Company.name))
        existing_names = {row[0].lower() for row in existing_result.all()}

        for c in track(companies_to_insert, description="Inserting companies..."):
            if c["name"].lower() in existing_names:
                stats["companies_skipped"] += 1
                continue
            company = Company(**{k: v for k, v in c.items()})
            session.add(company)
            existing_names.add(c["name"].lower())
            stats["companies_inserted"] += 1

        await session.commit()

    return stats


# ════════════════════════════════════════════════════════════
#  CLI Entry Point
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Seed the OutreachAI database with alternative protein companies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backend/scripts/seed_from_gfi.py
  python backend/scripts/seed_from_gfi.py --csv data/gfi_companies.csv
  python backend/scripts/seed_from_gfi.py --clear

Download GFI CSV from:
  https://gfi.org/resource/alternative-protein-company-database/
        """
    )
    parser.add_argument("--csv", metavar="PATH", help="Path to GFI CSV file (optional — uses bundled JSON if omitted)")
    parser.add_argument("--clear", action="store_true", help="Clear existing data before seeding")
    parser.add_argument("--json", metavar="PATH", help="Path to custom JSON seed file")
    args = parser.parse_args()

    # Force console encoding to UTF-8
    import sys
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    log("\n[bold]OutreachAI Seed Script[/bold]")
    log("[dim]Seeding alternative protein company database...[/dim]\n")

    async def run():
        if args.csv:
            stats = await seed_from_gfi_csv(args.csv, clear=args.clear)
        else:
            json_path = args.json or None
            stats = await seed_from_json(json_path, clear=args.clear)
        return stats

    stats = asyncio.run(run())

    if "error" in stats:
        log(f"\n[bold red]❌ Seed failed: {stats['error']}[/bold red]")
        sys.exit(1)

    log("\n[bold green]✅ Seed complete![/bold green]")

    # Pretty table
    try:
        table = Table(title="Seed Results")
        table.add_column("Category", style="cyan")
        table.add_column("Count", style="bold green", justify="right")
        table.add_row("Companies inserted", str(stats.get("companies_inserted", 0)))
        table.add_row("Companies skipped (dup)", str(stats.get("companies_skipped", 0)))
        table.add_row("Individuals inserted", str(stats.get("individuals_inserted", 0)))
        table.add_row("Individuals skipped (dup)", str(stats.get("individuals_skipped", 0)))
        console.print(table)
    except Exception:
        for k, v in stats.items():
            print(f"  {k}: {v}")

    log("\n[dim]Run the backend and open http://localhost:5173 to see your data.[/dim]")


if __name__ == "__main__":
    main()
