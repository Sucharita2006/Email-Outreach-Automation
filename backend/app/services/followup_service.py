"""
Follow-up Scheduler Service — Phase 7
Generates LLM-written follow-up emails for contacts who didn't reply.

Provides:
  - generate_follow_up(): LLM Call using followup.j2 template
  - process_due_follow_ups(): batch-process all overdue follow-ups
  - schedule_follow_up(): set follow_up_due_at on an email

Follow-up cadence (configurable in .env):
  FOLLOWUP_1_DAYS = 7   (1st follow-up: 7 days after original)
  FOLLOWUP_2_DAYS = 14  (2nd follow-up: 14 days after 1st, if still no reply)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database.models import (
    OutreachEmail, Individual, Company,
    EmailStatus, TargetType,
)
from app.services import llm_service, tracker_service
from app.services.gmail_service import create_draft as gmail_create_draft


async def generate_follow_up(
    original_email: OutreachEmail,
    db: AsyncSession,
) -> dict:
    """
    Generate a follow-up email draft using the followup.j2 template.
    Creates a new OutreachEmail record linked to the same campaign.

    Returns:
        {status, email_id, subject, body, follow_up_number}
    """
    # ── Load target individual ────────────────────────────────
    individual = None
    company_name = original_email.company_name or "your company"
    role = "Professional"

    if original_email.target_type == TargetType.INDIVIDUAL:
        result = await db.execute(
            select(Individual).where(Individual.id == original_email.target_id)
        )
        individual = result.scalar_one_or_none()
        if individual:
            role = individual.role or "Professional"

    recipient_name = original_email.recipient_name or "there"
    follow_up_number = (original_email.follow_up_count or 0) + 1

    # Calculate days elapsed since original was sent
    sent_at = original_email.sent_at or original_email.drafted_at
    days_elapsed = 0
    if sent_at:
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        days_elapsed = (datetime.now(timezone.utc) - sent_at).days

    # ── Render follow-up prompt ───────────────────────────────
    target_ctx = {
        "name": recipient_name,
        "role": role,
        "company": company_name,
    }
    original_ctx = {
        "sent_at": sent_at.strftime("%B %d, %Y") if sent_at else "recently",
        "subject": original_email.subject or "our previous email",
    }

    prompt = llm_service.render_prompt(
        "followup.j2",
        target=target_ctx,
        original_email=original_ctx,
        follow_up_number=follow_up_number,
        days_elapsed=days_elapsed,
        sender_name=settings.NONPROFIT_SENDER_NAME,
        sender_role=settings.NONPROFIT_SENDER_ROLE,
        nonprofit_name=settings.NONPROFIT_NAME,
    )

    # ── Call LLM ──────────────────────────────────────────────
    result = await llm_service.call_llm(
        prompt=prompt,
        temperature=0.4,
        max_tokens=400,
    )

    if result["status"] != "ok":
        return {
            "status": result["status"],
            "error": result.get("error"),
            "original_email_id": original_email.id,
        }

    # ── Parse subject + body ──────────────────────────────────
    from app.services.research_orchestrator import _parse_email_output
    subject, body = _parse_email_output(result["content"])

    # Default subject if parsing failed
    if not subject:
        subject = f"Re: {original_email.subject or 'Following up'}"

    # ── Save new OutreachEmail ────────────────────────────────
    now = datetime.now(timezone.utc)
    follow_up_email = OutreachEmail(
        campaign_id=original_email.campaign_id,
        target_type=original_email.target_type,
        target_id=original_email.target_id,
        recipient_email=original_email.recipient_email,
        recipient_name=original_email.recipient_name,
        company_name=original_email.company_name,
        subject=subject,
        body=body,
        status=EmailStatus.DRAFTED,
        drafted_at=now,
        llm_model_used=result.get("model"),
        notes=f"Follow-up #{follow_up_number} for email {original_email.id}",
    )
    db.add(follow_up_email)

    # ── Mark original as follow-up sent ──────────────────────
    await tracker_service.mark_follow_up_sent(original_email, db, follow_up_email_id=None)
    await db.flush()
    await db.refresh(follow_up_email)

    return {
        "status": "ok",
        "email_id": follow_up_email.id,
        "original_email_id": original_email.id,
        "follow_up_number": follow_up_number,
        "recipient_name": recipient_name,
        "recipient_email": original_email.recipient_email,
        "subject": subject,
        "body": body,
        "model": result.get("model"),
    }


async def process_due_follow_ups(
    db: AsyncSession,
    campaign_id: Optional[str] = None,
    push_to_gmail: bool = False,
    limit: int = 50,
) -> dict:
    """
    Find all emails due for a follow-up and generate drafts for them.

    Args:
        campaign_id: Optional — limit to one campaign.
        push_to_gmail: If True, also create Gmail drafts via Gmail API.
        limit: Max number of follow-ups to process in one run.

    Returns:
        Summary dict with processed count, generated drafts, errors.
    """
    due_emails = await tracker_service.get_due_follow_ups(db)

    # Filter by campaign if specified
    if campaign_id:
        due_emails = [e for e in due_emails if e.campaign_id == campaign_id]

    due_emails = due_emails[:limit]

    if not due_emails:
        return {
            "status": "ok",
            "message": "No follow-ups due at this time.",
            "processed": 0,
            "results": [],
        }

    results = []
    for email in due_emails:
        try:
            follow_up_result = await generate_follow_up(email, db)
            results.append(follow_up_result)

            # Optionally push to Gmail drafts
            if push_to_gmail and follow_up_result.get("status") == "ok":
                gmail_result = await gmail_create_draft(
                    to_email=follow_up_result.get("recipient_email", ""),
                    to_name=follow_up_result.get("recipient_name", ""),
                    subject=follow_up_result.get("subject", ""),
                    body=follow_up_result.get("body", ""),
                )
                follow_up_result["gmail"] = gmail_result

        except Exception as e:
            results.append({
                "status": "error",
                "original_email_id": email.id,
                "error": str(e),
            })

        await asyncio.sleep(0.5)  # Rate limiting between LLM calls

    await db.commit()

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    error_count = sum(1 for r in results if r.get("status") == "error")

    return {
        "status": "ok",
        "processed": len(due_emails),
        "generated": ok_count,
        "errors": error_count,
        "results": results,
    }


async def schedule_follow_up(
    email: OutreachEmail,
    db: AsyncSession,
    days: Optional[int] = None,
) -> dict:
    """
    Manually schedule a follow-up for an email at a specific number of days from now.
    Defaults to FOLLOWUP_1_DAYS if not specified.
    """
    now = datetime.now(timezone.utc)
    delay_days = days or settings.FOLLOWUP_1_DAYS
    follow_up_due = now + timedelta(days=delay_days)

    email.follow_up_due_at = follow_up_due
    if email.status == EmailStatus.SENT:
        email.status = EmailStatus.IGNORED  # Will trigger follow-up processor

    await db.flush()

    return {
        "status": "ok",
        "email_id": email.id,
        "follow_up_due_at": follow_up_due.isoformat(),
        "days_from_now": delay_days,
    }
