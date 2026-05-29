"""
SQLAlchemy Database Models — Phase 1
All tables: companies, individuals, outreach_campaigns, outreach_emails, reply_history
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.dialects.sqlite import JSON  # Use JSONB on PostgreSQL

import enum


# ── Base ─────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Helper: UUID primary key (stored as string for SQLite compat) ─
def new_uuid() -> str:
    return str(uuid.uuid4())


# ── Enums ────────────────────────────────────────────────────
class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class EmailStatus(str, enum.Enum):
    DRAFTED = "drafted"
    SENT = "sent"
    REPLIED = "replied"
    IGNORED = "ignored"
    FOLLOW_UP_SENT = "follow_up_sent"
    ARCHIVED = "archived"


class TargetType(str, enum.Enum):
    COMPANY = "company"
    INDIVIDUAL = "individual"


class DISCType(str, enum.Enum):
    D = "D"  # Dominant
    I = "I"  # Influential
    S = "S"  # Steady
    C = "C"  # Conscientious
    UNKNOWN = "UNKNOWN"


# ── Models ────────────────────────────────────────────────────

class SystemSetting(Base):
    """
    Stores global configuration and secrets like Gmail OAuth tokens.
    """
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<SystemSetting key={self.key}>"


class Company(Base):
    """
    Represents a company or organization that is a potential outreach target.
    Enriched from: GFI CSV, OpenCorporates, Serper, Hunter.io.
    """
    __tablename__ = "companies"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(255), nullable=False, index=True)

    # Advocacy domain tags (stored as JSON array: ["veganism", "plant-based"])
    domain_tags = Column(JSON, default=list)
    campaign_ids = Column(JSON, default=list)


    # Contact info
    website = Column(String(512))
    email = Column(String(255))           # Primary contact email (from Hunter)
    linkedin_url = Column(String(512))

    # Company profile
    description = Column(Text)
    industry = Column(String(255))
    size = Column(String(50))             # e.g., "50-200", "1-10"
    sector = Column(String(255))          # GFI sector: consumer brand, ingredient, etc.
    product_type = Column(String(255))    # GFI product type: plant-based meat, etc.

    # Relationship status
    known = Column(Boolean, default=False, nullable=False)
    last_contacted_at = Column(DateTime)

    # OpenCorporates enrichment
    opencorporates_id = Column(String(100))
    jurisdiction_code = Column(String(20))   # e.g., "us_de", "gb"
    company_status = Column(String(50))      # Active / Dissolved
    incorporation_date = Column(DateTime)
    company_type = Column(String(100))       # LLC, B Corp, Ltd, etc.
    registered_address = Column(Text)

    # Research cache (JSON blobs with TTL timestamps)
    hunter_domain_cache = Column(JSON)       # Cached Hunter domain search result
    serper_news_cache = Column(JSON)         # Cached Serper news results
    serper_web_cache = Column(JSON)          # Cached Serper web intelligence
    opencorporates_cache = Column(JSON)      # Cached OpenCorporates result
    company_analysis_cache = Column(JSON)   # Cached LLM Call 2 output (JSON)

    # Cache timestamps for TTL validation
    hunter_cached_at = Column(DateTime)
    serper_cached_at = Column(DateTime)
    opencorporates_cached_at = Column(DateTime)
    company_analysis_cached_at = Column(DateTime)

    # Metadata
    source = Column(String(100))             # "gfi_csv", "irs_bmf", "wikidata", "manual"
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    metadata_ = Column("metadata", JSON, default=dict)

    # Relationships
    individuals = relationship("Individual", back_populates="company", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name!r}>"


class Individual(Base):
    """
    Represents a specific person at a company — the actual email recipient.
    Enriched from: Hunter.io, Humantic AI, Serper, LinkedIn.
    """
    __tablename__ = "individuals"

    id = Column(String(36), primary_key=True, default=new_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)

    # Identity
    name = Column(String(255), nullable=False, index=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    role = Column(String(255))
    email = Column(String(255))
    email_confidence = Column(Float)         # Hunter.io confidence score (0-100)
    email_verified = Column(Boolean, default=False)  # Hunter verifier result
    linkedin_url = Column(String(512))

    # Domain tags (may differ from company — person could span domains)
    domain_tags = Column(JSON, default=list)
    campaign_ids = Column(JSON, default=list)


    # Relationship status
    known = Column(Boolean, default=False, nullable=False)
    last_contacted_at = Column(DateTime)

    # Research notes
    notes = Column(Text)

    # Humantic AI personality profiling
    humantic_disc = Column(Enum(DISCType), default=DISCType.UNKNOWN)
    humantic_big5 = Column(JSON)            # {"openness": 0.8, "conscientiousness": 0.7, ...}
    humantic_communication_pref = Column(Text)
    humantic_cached_at = Column(DateTime)

    # Serper individual signals
    serper_individual_cache = Column(JSON)  # Public mentions, articles, talks
    serper_cached_at = Column(DateTime)

    # LLM Call 1 cache (individual analysis)
    individual_analysis_cache = Column(JSON)  # {"key_hook": "...", "tone_instruction": "...", ...}
    individual_analysis_cached_at = Column(DateTime)

    # Metadata
    source = Column(String(100))            # "hunter", "gfi_csv", "manual"
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    metadata_ = Column("metadata", JSON, default=dict)

    # Relationships
    company = relationship("Company", back_populates="individuals")

    def __repr__(self) -> str:
        return f"<Individual id={self.id} name={self.name!r} email={self.email!r}>"


class OutreachCampaign(Base):
    """
    A campaign represents one outreach run targeting a specific advocacy domain.
    e.g., "veganism campaign - May 2026"
    """
    __tablename__ = "outreach_campaigns"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(255))                         # Optional human-readable name
    domain_target = Column(String(100), nullable=False, index=True)  # e.g., "veganism"
    purpose = Column(Text, default="")                  # Campaign purpose entered by user
    status = Column(Enum(CampaignStatus), default=CampaignStatus.DRAFT, nullable=False)
    created_by = Column(String(255))                   # User or org name
    total_targets = Column(Integer, default=0)
    total_drafted = Column(Integer, default=0)
    total_sent = Column(Integer, default=0)
    total_replied = Column(Integer, default=0)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    emails = relationship("OutreachEmail", back_populates="campaign", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<OutreachCampaign id={self.id} domain={self.domain_target!r} status={self.status}>"


class OutreachEmail(Base):
    """
    A single outreach email draft — generated by the LLM, reviewed by human, then sent.
    Tracks the full lifecycle: drafted → sent → replied/ignored → follow_up → archived.
    """
    __tablename__ = "outreach_emails"

    id = Column(String(36), primary_key=True, default=new_uuid)
    campaign_id = Column(String(36), ForeignKey("outreach_campaigns.id", ondelete="CASCADE"), nullable=False)

    # Target (company or individual)
    target_type = Column(Enum(TargetType), nullable=False)
    target_id = Column(String(36), nullable=False)  # FK to companies or individuals (polymorphic)
    recipient_email = Column(String(255))           # Denormalized for quick access
    recipient_name = Column(String(255))            # Denormalized for quick access
    company_name = Column(String(255))              # Denormalized for quick access

    # Email content
    subject = Column(String(500))
    body = Column(Text)

    # Status lifecycle
    status = Column(Enum(EmailStatus), default=EmailStatus.DRAFTED, nullable=False, index=True)

    # Timestamps
    drafted_at = Column(DateTime, default=func.now())
    sent_at = Column(DateTime)
    replied_at = Column(DateTime)
    follow_up_due_at = Column(DateTime)
    archived_at = Column(DateTime)

    # Follow-up tracking
    follow_up_count = Column(Integer, default=0)

    # Gmail integration
    gmail_draft_id = Column(String(255))

    # Review notes
    notes = Column(Text)

    # LLM generation metadata (for debugging)
    llm_model_used = Column(String(100))
    individual_analysis_snapshot = Column(JSON)  # Call 1 output used
    company_analysis_snapshot = Column(JSON)     # Call 2 output used

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    campaign = relationship("OutreachCampaign", back_populates="emails")
    reply_history = relationship("ReplyHistory", back_populates="email", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<OutreachEmail id={self.id} recipient={self.recipient_email!r} status={self.status}>"


class ReplyHistory(Base):
    """
    Records when and how a contact replied to outreach.
    Used to build "known" contact history for future campaigns.
    """
    __tablename__ = "reply_history"

    id = Column(String(36), primary_key=True, default=new_uuid)
    email_id = Column(String(36), ForeignKey("outreach_emails.id", ondelete="CASCADE"), nullable=False)

    reply_received_at = Column(DateTime, nullable=False)
    reply_snippet = Column(Text)        # First 500 chars of the reply
    domain_context = Column(String(100))  # The advocacy domain this reply relates to
    sentiment = Column(String(50))      # "positive", "neutral", "negative" (future use)
    notes = Column(Text)

    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    email = relationship("OutreachEmail", back_populates="reply_history")

    def __repr__(self) -> str:
        return f"<ReplyHistory id={self.id} email_id={self.email_id} received_at={self.reply_received_at}>"
