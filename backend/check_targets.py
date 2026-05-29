import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

async def check():
    engine = create_async_engine('sqlite+aiosqlite:///./outreach.db')
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        res = await session.execute(text("SELECT id, name, company_id FROM individuals WHERE name IN ('Melanie Joy', 'Priya Sawhney')"))
        inds = res.fetchall()
        print('Individuals:', inds)
        
        cids = [i[2] for i in inds if i[2]]
        if cids:
            res2 = await session.execute(text("SELECT id, name FROM companies"))
            comps = res2.fetchall()
            print('Companies:', [c for c in comps if c[0] in cids])

asyncio.run(check())
