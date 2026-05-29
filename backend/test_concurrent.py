import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database.models import Company

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

async def check():
    engine = create_async_engine('sqlite+aiosqlite:///./outreach.db')
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    # 1. Create a company
    async with async_session() as session:
        company = Company(name="Shared Company")
        session.add(company)
        await session.commit()
        comp_id = company.id

    # 2. Simulate concurrent tasks
    async def task(val):
        async with async_session() as session:
            c = await session.get(Company, comp_id)
            # Sleep slightly to ensure both load before either commits
            await asyncio.sleep(0.5)
            c.company_analysis_cache = {"val": val}
            try:
                await session.flush()
                await session.commit()
                print(f"Task {val} success")
            except Exception as e:
                print(f"Task {val} failed: {type(e).__name__}: {e}")

    await asyncio.gather(task(1), task(2))

asyncio.run(check())
