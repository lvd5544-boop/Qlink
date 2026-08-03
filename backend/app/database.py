import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://appuser:apppassword@localhost:5432/jobplatform"
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Some legacy synchronous parsing paths execute the async Model Gateway in a
# worker-owned event loop. Asyncpg pooled connections cannot safely move
# between that loop and Uvicorn's request loop, so audit writes use an
# unpooled engine. NullPool opens and closes a connection per write and keeps
# the primary request pool isolated.
audit_engine = create_async_engine(DATABASE_URL, echo=False, poolclass=NullPool)
AsyncAuditSessionLocal = async_sessionmaker(
    audit_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
