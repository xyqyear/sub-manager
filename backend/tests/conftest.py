from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.main import app
from app.models import (
    DialerOverrideRule,
    FilteredGroup,
    FilteredGroupRule,
    MainConfig,
    MainConfigSubscriptionLink,
    ManualGroup,
    ManualGroupMember,
    RuleSource,
    ShuntBinding,
    SubscriptionSource,
)


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
        await db.execute(delete(MainConfigSubscriptionLink))
        await db.execute(delete(FilteredGroupRule))
        await db.execute(delete(FilteredGroup))
        await db.execute(delete(ManualGroupMember))
        await db.execute(delete(ManualGroup))
        await db.execute(delete(DialerOverrideRule))
        await db.execute(delete(ShuntBinding))
        await db.execute(delete(MainConfig))
        await db.execute(delete(RuleSource))
        await db.execute(delete(SubscriptionSource))
        await db.commit()
