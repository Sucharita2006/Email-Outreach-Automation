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
    
    async with async_session() as session:
        company = Company(name="Test Placeholder")
        session.add(company)
        await session.flush()
        print(f"Company ID after flush: {company.id}")
        
        # update it
        company.company_analysis_cache = {"some": "data"}
        try:
            await session.flush()
            print("Update successful")
        except Exception as e:
            print(f"Update failed: {e}")

asyncio.run(check())
