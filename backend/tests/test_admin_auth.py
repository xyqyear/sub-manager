from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_admin_health_requires_token(client):
    response = await client.get("/api/admin/health")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_health_with_token(client, admin_headers):
    response = await client.get("/api/admin/health", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
