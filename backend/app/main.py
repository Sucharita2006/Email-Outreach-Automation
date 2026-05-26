"""
Email Outreach Automation — FastAPI Application Entry Point
Complete implementation with APScheduler background job for follow-up automation.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.session import init_db
from app.routers import targets, research, emails, campaigns, tracking
from app.config import settings

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#  APScheduler — Follow-up Background Job
# ════════════════════════════════════════════════════════════

def _start_scheduler():
    """
    Start APScheduler with a daily follow-up processing job.
    Runs every day at 08:00 AM to process overdue follow-ups.
    Safe to call multiple times (idempotent via replace_existing).
    """
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        import asyncio

        scheduler = AsyncIOScheduler()

        async def _daily_followup_job():
            """Daily job: find overdue follow-ups and generate LLM drafts."""
            from app.database.session import AsyncSessionLocal
            from app.services.followup_service import process_due_follow_ups

            logger.info("[Scheduler] Running daily follow-up job...")
            try:
                async with AsyncSessionLocal() as db:
                    result = await process_due_follow_ups(db=db, push_to_gmail=False)
                    logger.info(
                        f"[Scheduler] Follow-up job done: "
                        f"{result.get('generated', 0)} generated, "
                        f"{result.get('errors', 0)} errors"
                    )
            except Exception as e:
                logger.error(f"[Scheduler] Follow-up job failed: {e}")

        # Run daily at 08:00 AM
        scheduler.add_job(
            _daily_followup_job,
            trigger=CronTrigger(hour=8, minute=0),
            id="daily_followup",
            name="Daily Follow-up Processor",
            replace_existing=True,
            misfire_grace_time=3600,  # Run up to 1h late if server was down
        )

        scheduler.start()
        logger.info("[Scheduler] APScheduler started — daily follow-ups at 08:00 AM")
        return scheduler

    except ImportError:
        logger.warning("[Scheduler] APScheduler not installed. Skipping background jobs.")
        return None
    except Exception as e:
        logger.warning(f"[Scheduler] Failed to start scheduler: {e}")
        return None


# ════════════════════════════════════════════════════════════
#  Application Lifespan
# ════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    - Startup: Init DB tables, start APScheduler
    - Teardown: Shut down scheduler cleanly
    """
    # ── Startup ───────────────────────────────────────────────
    await init_db()
    logger.info("[Startup] Database initialized")

    scheduler = _start_scheduler()
    app.state.scheduler = scheduler

    yield

    # ── Teardown ──────────────────────────────────────────────
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Shutdown] APScheduler stopped")


# ════════════════════════════════════════════════════════════
#  FastAPI App
# ════════════════════════════════════════════════════════════

app = FastAPI(
    title="OutreachAI — Email Outreach Automation API",
    description=(
        "Open-source tool for animal advocacy nonprofits to conduct "
        "domain-targeted cold email outreach at scale.\n\n"
        "**Pipeline:** Target Discovery → Research Enrichment → "
        "3-Call LLM Draft → Human Review → Gmail Push → "
        "Reply Tracking → Follow-up Automation"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "OutreachAI",
        "url": "https://github.com/Sucharita2006/Email-Outreach-Automation",
    },
    license_info={"name": "MIT"},
)

# ── CORS Middleware ───────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite dev server
        "http://localhost:3000",    # Alternative frontend port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────
app.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
app.include_router(targets.router,   prefix="/targets",   tags=["Targets"])
app.include_router(research.router,  prefix="/research",  tags=["Research"])
app.include_router(emails.router,    prefix="/emails",    tags=["Emails"])
app.include_router(tracking.router,  prefix="/tracking",  tags=["Tracking"])


# ── Health Check ─────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    """Health check — returns app status and scheduler state."""
    scheduler = getattr(app.state, "scheduler", None)
    return {
        "status": "ok",
        "version": "1.0.0",
        "environment": settings.APP_ENV,
        "scheduler": {
            "running": bool(scheduler and scheduler.running),
            "jobs": (
                [j.name for j in scheduler.get_jobs()]
                if scheduler and scheduler.running else []
            ),
        },
        "api_keys_configured": {
            "openrouter": bool(settings.OPENROUTER_API_KEY),
            "hunter":     bool(settings.HUNTER_API_KEY),
            "serper":     bool(settings.SERPER_API_KEY),
            "opencorporates": bool(settings.OPENCORPORATES_API_TOKEN),
            "humantic":   bool(settings.HUMANTIC_API_KEY),
            "gmail":      bool(settings.GMAIL_CLIENT_ID and settings.GMAIL_CLIENT_SECRET),
        },
    }


@app.get("/", tags=["System"])
async def root():
    """Root — points to API docs."""
    return {
        "message": "OutreachAI — Email Outreach Automation API",
        "docs": "/docs",
        "health": "/health",
        "github": "https://github.com/Sucharita2006/Email-Outreach-Automation",
    }
