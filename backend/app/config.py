"""
Application configuration — loads from .env via pydantic-settings.
All settings accessed via: from app.config import settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    SECRET_KEY: str = "change_this_to_a_random_secret_key"

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./outreach.db"

    # ── OpenRouter ────────────────────────────────────────────
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_PRIMARY_MODEL: str = "anthropic/claude-3.5-sonnet"
    OPENROUTER_FALLBACK_MODEL: str = "meta-llama/llama-3.1-70b-instruct"
    OPENROUTER_BATCH_MODEL: str = "google/gemini-flash-1.5"

    # ── Hunter.io ─────────────────────────────────────────────
    HUNTER_API_KEY: str = ""
    HUNTER_BASE_URL: str = "https://api.hunter.io/v2"

    # ── Serper ────────────────────────────────────────────────
    SERPER_API_KEY: str = ""
    SERPER_BASE_URL: str = "https://google.serper.dev"

    # ── OpenCorporates ────────────────────────────────────────
    OPENCORPORATES_API_TOKEN: str = ""
    OPENCORPORATES_BASE_URL: str = "https://api.opencorporates.com/v0.4"

    # ── Humantic AI ───────────────────────────────────────────
    HUMANTIC_API_KEY: str = ""
    HUMANTIC_BASE_URL: str = "https://api.humantic.ai/v1"

    # ── Gmail ─────────────────────────────────────────────────
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REDIRECT_URI: str = "http://localhost:8000/auth/gmail/callback"

    # ── Nonprofit Profile ─────────────────────────────────────
    NONPROFIT_NAME: str = "Your Organization"
    NONPROFIT_MISSION: str = "Our mission is to advocate for animals."
    NONPROFIT_SENDER_NAME: str = "Outreach Team"
    NONPROFIT_SENDER_ROLE: str = "Outreach Coordinator"

    # ── Cache TTLs (seconds) ──────────────────────────────────
    HUNTER_CACHE_TTL_SECONDS: int = 1_209_600       # 14 days
    SERPER_CACHE_TTL_SECONDS: int = 604_800          # 7 days
    OPENCORPORATES_CACHE_TTL_SECONDS: int = 2_592_000 # 30 days
    HUMANTIC_CACHE_TTL_SECONDS: int = 7_776_000      # 90 days
    INDIVIDUAL_ANALYSIS_CACHE_TTL_SECONDS: int = 2_592_000  # 30 days
    COMPANY_ANALYSIS_CACHE_TTL_SECONDS: int = 604_800       # 7 days

    # ── Rate Limiting ─────────────────────────────────────────
    LLM_BATCH_CONCURRENCY: int = 10
    RESEARCH_BATCH_CONCURRENCY: int = 5

    # ── Follow-up Scheduling (days) ───────────────────────────
    FOLLOWUP_1_DAYS: int = 7
    FOLLOWUP_2_DAYS: int = 14


# Singleton instance — import this everywhere
settings = Settings()
