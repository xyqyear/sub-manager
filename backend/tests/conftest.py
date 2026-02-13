from __future__ import annotations

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

TEST_DB_PATH = Path("/tmp/sub_manager_test.sqlite3")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

from app.config import settings
from app.db.database import AsyncSessionLocal, engine, init_db
from app.main import app
from app.models import (
    MainConfig,
    RuleSource,
    SubscriptionSource,
)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_database() -> None:
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    await init_db()
    yield

    await engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.admin_token}"}


@pytest.fixture(autouse=True)
async def clean_db() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(MainConfig))
        await db.execute(delete(RuleSource))
        await db.execute(delete(SubscriptionSource))
        await db.commit()
