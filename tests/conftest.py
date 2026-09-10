from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy.pool import StaticPool

from src.accounts.bootstrap import seed_user_groups
from src.database import Base, get_db
from src.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def _session_maker():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with session_maker() as session:
        await seed_user_groups(session)

    yield session_maker
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_session_maker) -> AsyncGenerator[AsyncSession, None]:
    """A session for making test-side assertions,
     independent of the app's own sessions."""
    async with _session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(_session_maker) -> AsyncGenerator[AsyncClient, None]:
    # Mirrors production behaviour: each request gets its own fresh session,
    # avoiding identity-map/staleness issues from sharing one session across requests.
    async def _override_get_db():
        async with _session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def strong_password() -> str:
    return "StrongPass1!"
