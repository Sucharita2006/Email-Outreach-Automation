"""
Database session management — async SQLAlchemy engine + session factory.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import event
from typing import AsyncGenerator

from app.config import settings
from app.database.models import Base


# ── Engine ────────────────────────────────────────────────────
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://") or db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://").replace("postgresql://", "postgresql+asyncpg://")

# For SQLite: use StaticPool ONLY for in-memory databases
is_sqlite = "sqlite" in db_url
is_memory = ":memory:" in db_url

engine = create_async_engine(
    db_url,
    echo=(settings.APP_ENV == "development"),  # SQL logging in dev only
    connect_args={
        "check_same_thread": False,
        "timeout": 30,  # Wait up to 30s for DB lock instead of failing immediately
    } if is_sqlite else {},
    poolclass=StaticPool if is_sqlite and is_memory else None,
)

# Enable WAL mode for file-based SQLite — allows concurrent reads + writes
if is_sqlite and not is_memory:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconds
        cursor.close()

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
