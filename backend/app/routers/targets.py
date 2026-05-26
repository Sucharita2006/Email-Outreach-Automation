"""
Targets Router — Phase 2: Full Implementation
- Company CRUD (list, get, create, update, delete)
- Individual CRUD (list, get, create, update, delete)
- Fuzzy domain search across companies + individuals
- Domain tag filtering, known/new badge, pagination
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, cast, String
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime

from app.database.session import get_db
from app.database.models import Company, Individual, DISCType
from app.utils.fuzzy_match import expand_domain_query

router = APIRouter()


# ════════════════════════════════════════════════════════════
#  Pydantic Schemas
# ════════════════════════════════════════════════════════════

class CompanyCreate(BaseModel):
    name: str
    domain_tags: list[str] = []
    website: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    sector: Optional[str] = None
    product_type: Optional[str] = None
    source: Optional[str] = "manual"


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    domain_tags: Optional[list[str]] = None
    website: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    sector: Optional[str] = None
    product_type: Optional[str] = None
    known: Optional[bool] = None


class CompanyRead(BaseModel):
    id: str
    name: str
    domain_tags: list[str]
    website: Optional[str]
    email: Optional[str]
    linkedin_url: Optional[str]
    description: Optional[str]
    industry: Optional[str]
    size: Optional[str]
    sector: Optional[str]
    product_type: Optional[str]
    known: bool
    last_contacted_at: Optional[datetime]
    company_status: Optional[str]
    jurisdiction_code: Optional[str]
    company_type: Optional[str]
    source: Optional[str]
    individual_count: Optional[int] = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class IndividualCreate(BaseModel):
    name: str
    company_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    domain_tags: list[str] = []
    notes: Optional[str] = None
    source: Optional[str] = "manual"


class IndividualUpdate(BaseModel):
    name: Optional[str] = None
    company_id: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    domain_tags: Optional[list[str]] = None
    notes: Optional[str] = None
    known: Optional[bool] = None


class IndividualRead(BaseModel):
    id: str
    company_id: Optional[str]
    name: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: Optional[str]
    email: Optional[str]
    email_confidence: Optional[float]
    email_verified: Optional[bool]
    linkedin_url: Optional[str]
    domain_tags: list[str]
    known: bool
    last_contacted_at: Optional[datetime]
    humantic_disc: Optional[str]
    notes: Optional[str]
    source: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class SearchResult(BaseModel):
    companies: list[CompanyRead]
    individuals: list[IndividualRead]
    total_companies: int
    total_individuals: int
    matched_domain_tags: list[str]
    query: str


# ════════════════════════════════════════════════════════════
#  Domain Search — Core Phase 2 Feature
# ════════════════════════════════════════════════════════════

@router.get("/search", response_model=SearchResult)
async def search_targets(
    domain: str = Query(..., description="Advocacy domain keyword e.g. 'veganism', 'plant-based'"),
    include_known: bool = Query(True, description="Include previously contacted targets"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Search companies AND individuals by advocacy domain keyword.
    Uses fuzzy matching to expand queries:
      - "vegan" → matches "veganism", "vegan-business", "cruelty-free"
      - "plant" → matches "plant-based", "alternative-protein"
    Returns a combined result with matched domain tags shown.
    """
    # Expand query using fuzzy taxonomy matching
    matched_tags = expand_domain_query(domain)

    # ── Company search ────────────────────────────────────────
    company_stmt = select(Company)

    # SQLite JSON contains search: check if any matched tag is in domain_tags JSON
    # We cast to string and use LIKE for SQLite compatibility
    tag_conditions = [
        cast(Company.domain_tags, String).contains(tag)
        for tag in matched_tags
    ]
    company_stmt = company_stmt.where(or_(*tag_conditions))

    if not include_known:
        company_stmt = company_stmt.where(Company.known == False)

    company_stmt = company_stmt.order_by(
        Company.known.asc(),      # unknown/new targets first
        Company.name.asc()
    ).offset(offset).limit(limit)

    company_result = await db.execute(company_stmt)
    companies = company_result.scalars().all()

    # Count total
    count_stmt = select(func.count()).select_from(Company).where(or_(*tag_conditions))
    if not include_known:
        count_stmt = count_stmt.where(Company.known == False)
    total_companies = (await db.execute(count_stmt)).scalar_one()

    # ── Individual search ─────────────────────────────────────
    ind_stmt = select(Individual)
    ind_tag_conditions = [
        cast(Individual.domain_tags, String).contains(tag)
        for tag in matched_tags
    ]
    ind_stmt = ind_stmt.where(or_(*ind_tag_conditions))

    if not include_known:
        ind_stmt = ind_stmt.where(Individual.known == False)

    ind_stmt = ind_stmt.order_by(
        Individual.known.asc(),
        Individual.name.asc()
    ).offset(offset).limit(limit)

    ind_result = await db.execute(ind_stmt)
    individuals = ind_result.scalars().all()

    # Count total
    ind_count_stmt = select(func.count()).select_from(Individual).where(or_(*ind_tag_conditions))
    if not include_known:
        ind_count_stmt = ind_count_stmt.where(Individual.known == False)
    total_individuals = (await db.execute(ind_count_stmt)).scalar_one()

    return SearchResult(
        companies=[CompanyRead.model_validate(c) for c in companies],
        individuals=[IndividualRead.model_validate(i) for i in individuals],
        total_companies=total_companies,
        total_individuals=total_individuals,
        matched_domain_tags=matched_tags,
        query=domain,
    )


# ════════════════════════════════════════════════════════════
#  Company CRUD
# ════════════════════════════════════════════════════════════

@router.get("/companies", response_model=list[CompanyRead])
async def list_companies(
    domain_tag: Optional[str] = Query(None, description="Filter by exact domain tag"),
    known: Optional[bool] = Query(None, description="Filter by known status"),
    search: Optional[str] = Query(None, description="Name contains search"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all companies with optional filters."""
    stmt = select(Company)

    if domain_tag:
        stmt = stmt.where(cast(Company.domain_tags, String).contains(domain_tag))
    if known is not None:
        stmt = stmt.where(Company.known == known)
    if search:
        stmt = stmt.where(Company.name.ilike(f"%{search}%"))

    stmt = stmt.order_by(Company.known.asc(), Company.name.asc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/companies/{company_id}", response_model=CompanyRead)
async def get_company(company_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single company by ID."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.post("/companies", response_model=CompanyRead, status_code=201)
async def create_company(data: CompanyCreate, db: AsyncSession = Depends(get_db)):
    """Manually add a company to the database."""
    company = Company(**data.model_dump())
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


@router.patch("/companies/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: str,
    data: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update company fields."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)

    await db.flush()
    await db.refresh(company)
    return company


@router.delete("/companies/{company_id}", status_code=204)
async def delete_company(company_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a company and all associated individuals."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    await db.delete(company)


@router.post("/companies/{company_id}/mark-known", response_model=CompanyRead)
async def mark_company_known(company_id: str, db: AsyncSession = Depends(get_db)):
    """Mark a company as a known contact."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company.known = True
    company.last_contacted_at = datetime.utcnow()
    await db.flush()
    await db.refresh(company)
    return company


# ════════════════════════════════════════════════════════════
#  Individual CRUD
# ════════════════════════════════════════════════════════════

@router.get("/individuals", response_model=list[IndividualRead])
async def list_individuals(
    company_id: Optional[str] = Query(None, description="Filter by company ID"),
    domain_tag: Optional[str] = Query(None, description="Filter by domain tag"),
    known: Optional[bool] = Query(None, description="Filter by known status"),
    search: Optional[str] = Query(None, description="Name or email contains search"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List individuals with optional filters."""
    stmt = select(Individual)

    if company_id:
        stmt = stmt.where(Individual.company_id == company_id)
    if domain_tag:
        stmt = stmt.where(cast(Individual.domain_tags, String).contains(domain_tag))
    if known is not None:
        stmt = stmt.where(Individual.known == known)
    if search:
        stmt = stmt.where(
            or_(
                Individual.name.ilike(f"%{search}%"),
                Individual.email.ilike(f"%{search}%"),
                Individual.role.ilike(f"%{search}%"),
            )
        )

    stmt = stmt.order_by(Individual.known.asc(), Individual.name.asc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/individuals/{individual_id}", response_model=IndividualRead)
async def get_individual(individual_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single individual by ID."""
    result = await db.execute(select(Individual).where(Individual.id == individual_id))
    individual = result.scalar_one_or_none()
    if not individual:
        raise HTTPException(status_code=404, detail="Individual not found")
    return individual


@router.post("/individuals", response_model=IndividualRead, status_code=201)
async def create_individual(data: IndividualCreate, db: AsyncSession = Depends(get_db)):
    """Manually add an individual to the database."""
    # Validate company exists if company_id provided
    if data.company_id:
        comp = await db.execute(select(Company).where(Company.id == data.company_id))
        if not comp.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Company not found")

    individual = Individual(**data.model_dump())
    db.add(individual)
    await db.flush()
    await db.refresh(individual)
    return individual


@router.patch("/individuals/{individual_id}", response_model=IndividualRead)
async def update_individual(
    individual_id: str,
    data: IndividualUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update individual fields."""
    result = await db.execute(select(Individual).where(Individual.id == individual_id))
    individual = result.scalar_one_or_none()
    if not individual:
        raise HTTPException(status_code=404, detail="Individual not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(individual, field, value)

    await db.flush()
    await db.refresh(individual)
    return individual


@router.delete("/individuals/{individual_id}", status_code=204)
async def delete_individual(individual_id: str, db: AsyncSession = Depends(get_db)):
    """Delete an individual."""
    result = await db.execute(select(Individual).where(Individual.id == individual_id))
    individual = result.scalar_one_or_none()
    if not individual:
        raise HTTPException(status_code=404, detail="Individual not found")
    await db.delete(individual)


@router.post("/individuals/{individual_id}/mark-known", response_model=IndividualRead)
async def mark_individual_known(individual_id: str, db: AsyncSession = Depends(get_db)):
    """Mark an individual as a known contact."""
    result = await db.execute(select(Individual).where(Individual.id == individual_id))
    individual = result.scalar_one_or_none()
    if not individual:
        raise HTTPException(status_code=404, detail="Individual not found")
    individual.known = True
    individual.last_contacted_at = datetime.utcnow()
    await db.flush()
    await db.refresh(individual)
    return individual


# ════════════════════════════════════════════════════════════
#  Stats
# ════════════════════════════════════════════════════════════

@router.get("/stats")
async def target_stats(db: AsyncSession = Depends(get_db)):
    """Return database-wide target stats."""
    total_companies = (await db.execute(select(func.count()).select_from(Company))).scalar_one()
    known_companies = (await db.execute(select(func.count()).select_from(Company).where(Company.known == True))).scalar_one()
    total_individuals = (await db.execute(select(func.count()).select_from(Individual))).scalar_one()
    known_individuals = (await db.execute(select(func.count()).select_from(Individual).where(Individual.known == True))).scalar_one()

    return {
        "companies": {
            "total": total_companies,
            "known": known_companies,
            "new": total_companies - known_companies,
        },
        "individuals": {
            "total": total_individuals,
            "known": known_individuals,
            "new": total_individuals - known_individuals,
        },
    }
