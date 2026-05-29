"""
Reply Tracker Service — Phase 7
Handles manual and automatic reply detection, status updates,
and reply history logging.

Provides:
  - mark_replied(): mark email as replied, update known status, log history
  - mark_ignored(): mark email as ignored, schedule follow-up
  - mark_follow_up_sent(): record that a follow-up was sent
  - get_reply_history(): fetch all replies for a contact
  - tracking_dashboard(): aggregate stats per campaign
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config import settings
from app.database.models import (
    OutreachEmail, ReplyHistory, Individual, Company,
    EmailStatus, TargetType,
)


async def mark_replied(
    email: OutreachEmail,
    db: AsyncSession,
    reply_snippet: str = "",
    sentiment: str = "neutral",
) -> dict:
    """
    Mark an outreach email as replied.
    - Updates email status → 'replied'
    - Sets replied_at timestamp
    - Creates a ReplyHistory record
    - Marks the target individual/company as 'known' (known=True)

    Args:
        email: The OutreachEmail instance.
        reply_snippet: First ~500 chars of the reply email body.
        sentiment: "positive", "neutral", or "negative".

    Returns:
        Summary dict with updated status.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # ── Update email status ───────────────────────────────────
    email.status = EmailStatus.REPLIED
    email.replied_at = now

    # ── Log to reply_history ──────────────────────────────────
    reply_record = ReplyHistory(
        email_id=email.id,
        reply_received_at=now,
        reply_snippet=reply_snippet or "",
        domain_context=_get_campaign_domain(email, db),
        sentiment=sentiment,
        notes=None,
    )
    db.add(reply_record)

    # ── Mark target as 'known' ────────────────────────────────
    known_result = await _mark_target_known(email, db, now)

    await db.flush()

    return {
        "status": "ok",
        "email_id": email.id,
        "new_status": "replied",
        "replied_at": now.isoformat(),
        "target_marked_known": known_result,
        "sentiment": sentiment,
    }


async def mark_ignored(
    email: OutreachEmail,
    db: AsyncSession,
    schedule_follow_up: bool = True,
) -> dict:
    """
    Mark an outreach email as ignored (no reply received).
    Optionally schedules a follow-up based on FOLLOWUP_1_DAYS config.

    Returns:
        Summary dict with follow-up due date if scheduled.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    email.status = EmailStatus.IGNORED

    follow_up_due = None
    if schedule_follow_up and email.follow_up_count == 0:
        follow_up_days = settings.FOLLOWUP_1_DAYS
        follow_up_due = now + timedelta(days=follow_up_days)
        email.follow_up_due_at = follow_up_due

    await db.flush()

    return {
        "status": "ok",
        "email_id": email.id,
        "new_status": "ignored",
        "follow_up_scheduled": schedule_follow_up and follow_up_due is not None,
        "follow_up_due_at": follow_up_due.isoformat() if follow_up_due else None,
        "follow_up_days": settings.FOLLOWUP_1_DAYS if schedule_follow_up else None,
    }


async def mark_follow_up_sent(
    email: OutreachEmail,
    db: AsyncSession,
    follow_up_email_id: str = None,
) -> dict:
    """
    Record that a follow-up email was sent for this original email.
    Updates follow_up_count and schedules a second follow-up if applicable.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    email.status = EmailStatus.FOLLOW_UP_SENT
    email.follow_up_count = (email.follow_up_count or 0) + 1

    # Schedule 2nd follow-up if this was the first
    follow_up_due = None
    if email.follow_up_count == 1:
        follow_up_days = settings.FOLLOWUP_2_DAYS
        follow_up_due = now + timedelta(days=follow_up_days)
        email.follow_up_due_at = follow_up_due

    await db.flush()

    return {
        "status": "ok",
        "email_id": email.id,
        "follow_up_count": email.follow_up_count,
        "second_follow_up_due_at": follow_up_due.isoformat() if follow_up_due else None,
    }


async def get_due_follow_ups(db: AsyncSession) -> list[OutreachEmail]:
    """
    Return all emails that are due for a follow-up right now.
    Conditions:
      - status is 'ignored' or 'sent'
      - follow_up_due_at <= now
      - follow_up_count < 2 (max 2 follow-ups)
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stmt = (
        select(OutreachEmail)
        .where(
            OutreachEmail.status.in_([EmailStatus.IGNORED, EmailStatus.SENT]),
            OutreachEmail.follow_up_due_at <= now,
            OutreachEmail.follow_up_count < 2,
        )
        .order_by(OutreachEmail.follow_up_due_at.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_reply_history(
    target_id: str,
    db: AsyncSession,
) -> list[dict]:
    """
    Get the full reply history for a target (individual or company).
    Joins ReplyHistory → OutreachEmail → target.
    """
    stmt = (
        select(ReplyHistory, OutreachEmail)
        .join(OutreachEmail, ReplyHistory.email_id == OutreachEmail.id)
        .where(OutreachEmail.target_id == target_id)
        .order_by(ReplyHistory.reply_received_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "reply_id": rh.id,
            "email_id": email.id,
            "subject": email.subject,
            "reply_received_at": rh.reply_received_at.isoformat(),
            "reply_snippet": rh.reply_snippet,
            "sentiment": rh.sentiment,
            "domain_context": rh.domain_context,
        }
        for rh, email in rows
    ]


async def tracking_dashboard(
    campaign_id: Optional[str],
    db: AsyncSession,
) -> dict:
    """
    Return aggregate reply/ignore/pending stats, optionally filtered by campaign.
    Used by the frontend tracking dashboard.
    """
    base = select(OutreachEmail)
    if campaign_id:
        base = base.where(OutreachEmail.campaign_id == campaign_id)

    async def _count(status_filter=None):
        stmt = select(func.count()).select_from(OutreachEmail)
        if campaign_id:
            stmt = stmt.where(OutreachEmail.campaign_id == campaign_id)
        if status_filter:
            if isinstance(status_filter, list):
                stmt = stmt.where(OutreachEmail.status.in_(status_filter))
            else:
                stmt = stmt.where(OutreachEmail.status == status_filter)
        return (await db.execute(stmt)).scalar_one()

    total = await _count()
    drafted = await _count(EmailStatus.DRAFTED)
    sent = await _count([EmailStatus.SENT, EmailStatus.REPLIED, EmailStatus.IGNORED, EmailStatus.FOLLOW_UP_SENT])
    replied = await _count(EmailStatus.REPLIED)
    ignored = await _count(EmailStatus.IGNORED)
    follow_up_sent = await _count(EmailStatus.FOLLOW_UP_SENT)
    archived = await _count(EmailStatus.ARCHIVED)

    # Follow-ups due today
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    due_stmt = select(func.count()).select_from(OutreachEmail).where(
        OutreachEmail.status.in_([EmailStatus.IGNORED, EmailStatus.SENT]),
        OutreachEmail.follow_up_due_at <= now,
        OutreachEmail.follow_up_count < 2,
    )
    if campaign_id:
        due_stmt = due_stmt.where(OutreachEmail.campaign_id == campaign_id)
    follow_ups_due = (await db.execute(due_stmt)).scalar_one()

    reply_rate = round((replied / sent * 100), 1) if sent > 0 else 0.0

    return {
        "campaign_id": campaign_id,
        "totals": {
            "all": total,
            "drafted": drafted,
            "sent": sent,
            "replied": replied,
            "ignored": ignored,
            "follow_up_sent": follow_up_sent,
            "archived": archived,
        },
        "metrics": {
            "reply_rate_pct": reply_rate,
            "follow_ups_due_now": follow_ups_due,
            "pending_review": drafted,
        },
    }


# ════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════

def _get_campaign_domain(email: OutreachEmail, db) -> str:
    """Extract domain context from the email record (best-effort)."""
    return email.company_name or "general"


async def _mark_target_known(
    email: OutreachEmail,
    db: AsyncSession,
    now: datetime,
) -> str:
    """Mark the target individual or company as known=True after a reply."""
    if email.target_type == TargetType.INDIVIDUAL:
        result = await db.execute(select(Individual).where(Individual.id == email.target_id))
        target = result.scalar_one_or_none()
        if target:
            target.known = True
            target.last_contacted_at = now
            return f"Individual {target.name} marked known"
    elif email.target_type == TargetType.COMPANY:
        result = await db.execute(select(Company).where(Company.id == email.target_id))
        target = result.scalar_one_or_none()
        if target:
            target.known = True
            target.last_contacted_at = now
            return f"Company {target.name} marked known"
    return "Target not found"
