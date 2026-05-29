"""
Email Service — Phase 8 Final
Unified email management layer: wraps orchestrator + tracker + Gmail.

Provides:
  - send_email_draft(): mark an email as sent (human confirmed)
  - log_send(): write send log entry
  - export_email_text(): plain text for copy-paste
  - get_email_context(): full context for a draft (individual + company + history)
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import OutreachEmail, Individual, Company, ReplyHistory, EmailStatus
from app.services import gmail_service


async def send_email_draft(
    email: OutreachEmail,
    db: AsyncSession,
    push_to_gmail: bool = False,
) -> dict:
    """
    Mark a draft email as sent (human-confirmed action — no auto-send).
    Optionally push to Gmail drafts for one-click sending.

    Returns: {status, email_id, sent_at, gmail_draft_id}
    """
    if email.status != EmailStatus.DRAFTED:
        return {
            "status": "error",
            "message": f"Email is '{email.status}', not 'drafted'. Only drafted emails can be marked sent.",
        }

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    email.status = EmailStatus.SENT
    email.sent_at = now
    await db.flush()

    gmail_result = None
    if push_to_gmail and email.recipient_email:
        gmail_result = await gmail_service.create_draft(
            to_email=email.recipient_email,
            to_name=email.recipient_name or "",
            subject=email.subject or "",
            body=email.body or "",
        )
        if gmail_result.get("status") == "ok":
            email.gmail_draft_id = gmail_result.get("draft_id")
            await db.flush()

    await db.commit()

    return {
        "status": "ok",
        "email_id": email.id,
        "sent_at": now.isoformat(),
        "recipient_email": email.recipient_email,
        "recipient_name": email.recipient_name,
        "gmail": gmail_result,
    }


def export_email_text(email: OutreachEmail) -> str:
    """
    Export a draft email as plain text — ready for copy-paste into Gmail, Outlook, etc.
    Format:
        To: Name <email>
        Subject: ...
        ----
        [body]
    """
    lines = []
    if email.recipient_name or email.recipient_email:
        to_str = email.recipient_name or ""
        if email.recipient_email:
            to_str = f"{email.recipient_name} <{email.recipient_email}>" if email.recipient_name else email.recipient_email
        lines.append(f"To: {to_str}")
    lines.append(f"Subject: {email.subject or 'No subject'}")
    lines.append("-" * 60)
    lines.append("")
    lines.append((email.body or "").strip())
    return "\n".join(lines)


async def get_email_context(email_id: str, db: AsyncSession) -> dict:
    """
    Return full enriched context for an email draft:
    - The email record
    - The individual's profile
    - The company profile
    - Reply history for this contact
    - Cached LLM analysis snapshots
    """
    result = await db.execute(select(OutreachEmail).where(OutreachEmail.id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        return {"status": "not_found"}

    individual = None
    company = None
    reply_history = []

    # Load individual
    ind_result = await db.execute(select(Individual).where(Individual.id == email.target_id))
    individual = ind_result.scalar_one_or_none()

    # Load company by name (best effort)
    if email.company_name:
        comp_result = await db.execute(select(Company).where(Company.name == email.company_name))
        company = comp_result.scalar_one_or_none()

    # Load reply history for this target
    rh_result = await db.execute(
        select(ReplyHistory)
        .join(OutreachEmail, ReplyHistory.email_id == OutreachEmail.id)
        .where(OutreachEmail.target_id == email.target_id)
        .order_by(ReplyHistory.reply_received_at.desc())
        .limit(5)
    )
    reply_records = rh_result.scalars().all()
    reply_history = [
        {
            "reply_received_at": r.reply_received_at.isoformat(),
            "snippet": r.reply_snippet,
            "sentiment": r.sentiment,
        }
        for r in reply_records
    ]

    return {
        "status": "ok",
        "email": {
            "id": email.id,
            "subject": email.subject,
            "body": email.body,
            "status": email.status,
            "drafted_at": email.drafted_at.isoformat() if email.drafted_at else None,
            "sent_at": email.sent_at.isoformat() if email.sent_at else None,
            "llm_model_used": email.llm_model_used,
            "notes": email.notes,
        },
        "individual": {
            "id": individual.id if individual else None,
            "name": individual.name if individual else email.recipient_name,
            "role": individual.role if individual else None,
            "email": individual.email if individual else email.recipient_email,
            "disc_type": individual.humantic_disc if individual else None,
            "communication_pref": individual.humantic_communication_pref if individual else None,
            "linkedin_url": individual.linkedin_url if individual else None,
        },
        "company": {
            "id": company.id if company else None,
            "name": company.name if company else email.company_name,
            "sector": company.sector if company else None,
            "product_type": company.product_type if company else None,
            "website": company.website if company else None,
        },
        "individual_analysis": email.individual_analysis_snapshot,
        "company_analysis": email.company_analysis_snapshot,
        "reply_history": reply_history,
    }
