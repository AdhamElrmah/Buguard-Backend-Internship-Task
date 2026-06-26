import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.database import Base, get_db
from app.main import app

# Test database URL (uses darkatlas_test database)
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@localhost:5433/darkatlas_test"

# Create async engine for test database
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

@pytest.fixture(scope="session")
def event_loop():
    """
    Create a session-scoped event loop to resolve ScopeMismatch errors
    in pytest-asyncio when using session-scoped fixtures.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """
    Setup the database tables before running the test suite,
    and drop them afterwards.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()

@pytest.fixture(autouse=True)
async def clean_db():
    """
    Truncate all tables before each test to ensure test isolation.
    """
    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE relationships, assets RESTART IDENTITY CASCADE;"))

@pytest.fixture
async def db():
    """
    Provide an AsyncSession instance connected to the test database.
    """
    async with test_session_factory() as session:
        yield session

@pytest.fixture
async def client(db):
    """
    Provide an AsyncClient for testing API endpoints with dependency overrides.
    """
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest.fixture
def auth_headers():
    """
    Headers required for write operations (authentication).
    """
    return {"X-API-Key": settings.API_KEY}
