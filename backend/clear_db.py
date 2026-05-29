import asyncio
import logging
from sqlalchemy import text
from app.database.session import engine, Base
from app.database.models import OutreachEmail, TargetIndividual, TargetCompany, Campaign, SystemSetting

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clear_database():
    logger.info("Connecting to the database...")
    async with engine.begin() as conn:
        logger.info("Dropping all tables...")
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("Recreating all tables...")
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database cleared successfully!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(clear_database())
