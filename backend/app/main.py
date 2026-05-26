"""
Email Outreach Automation — FastAPI Application Entry Point
Phase 1: Core setup, router registration, startup events
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.session import init_db
from app.routers import targets, research, emails, campaigns, tracking
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Runs startup logic before yield, teardown logic after.
    """
    # ── Startup ───────────────────────────────────────────────
    await init_db()
    yield
    # ── Teardown (if needed in future) ────────────────────────


app = FastAPI(
    title="Email Outreach Automation API",
    description=(
        "Open-source tool for animal advocacy nonprofits to conduct "
        "domain-targeted cold email outreach at scale."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS Middleware ───────────────────────────────────────────
# Allows the React frontend (localhost:5173) to communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # Alternative frontend port
        "http://127.0.0.1:5173",
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
    """Basic health check endpoint."""
    return {
        "status": "ok",
        "version": "0.1.0",
        "environment": settings.APP_ENV,
    }


@app.get("/", tags=["System"])
async def root():
    """Root endpoint — points to API docs."""
    return {
        "message": "Email Outreach Automation API",
        "docs": "/docs",
        "health": "/health",
    }
