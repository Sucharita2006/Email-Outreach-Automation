import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from app.database.session import Base
from app.database.models import *

async def clear_db():
    engine = create_async_engine("sqlite+aiosqlite:///./outreach.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("Database cleared successfully.")

if __name__ == "__main__":
    asyncio.run(clear_db())
