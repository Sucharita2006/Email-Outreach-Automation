"""
Database session management — async SQLAlchemy engine + session factory.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from typing import AsyncGenerator

from app.config import settings
from app.database.models import Base


# ── Engine ────────────────────────────────────────────────────
# For SQLite: use StaticPool to share connections safely in tests
# For PostgreSQL: remove StaticPool and connect_args
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.APP_ENV == "development"),  # SQL logging in dev only
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    poolclass=StaticPool if "sqlite" in settings.DATABASE_URL else None,
)

# ── Session Factory ───────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── DB Initialization ─────────────────────────────────────────
async def init_db() -> None:
    """
    Create all tables on startup if they don't exist.
    In production, use Alembic migrations instead.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Dependency ────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an async DB session.
    Usage in routers:
        from app.database.session import get_db
        async def route(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
