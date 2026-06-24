from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# --- Engine ---
# The engine manages a pool of database connections.
# - echo=True logs all SQL queries to stdout (useful for debugging, disable in production)
# - pool_size=5 keeps 5 connections open and ready
# - max_overflow=10 allows up to 10 extra connections under heavy load
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=10,
)

# --- Session Factory ---
# Creates new AsyncSession instances with consistent settings.
# - expire_on_commit=False: after committing, the objects remain usable
#   without triggering a new database query. This is important for returning
#   data to the client after a commit.
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# --- Base Model ---
# All SQLAlchemy ORM models will inherit from this class.
# Alembic uses this to auto-detect which tables should exist.
class Base(DeclarativeBase):
    pass


# --- Dependency Injection ---
# FastAPI calls this for every request that needs a database session.
# The `yield` keyword makes this a generator:
#   1. Before yield: create the session
#   2. yield: the route handler runs and uses the session
#   3. After yield (finally): close the session, releasing the connection back to the pool
async def get_db():
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
