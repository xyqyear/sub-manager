from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_token
from app.db.database import get_db
from app.schemas.configs import AdminHealthResponse
from app.services.refresh_loop import refresh_loop_manager

router = APIRouter(prefix="/admin", tags=["admin-health"], dependencies=[Depends(require_admin_token)])


@router.get("/health", response_model=AdminHealthResponse)
async def admin_health(db: AsyncSession = Depends(get_db)) -> AdminHealthResponse:
    await db.execute(text("SELECT 1"))
    return AdminHealthResponse(
        status="ok",
        refresh_loop_running=refresh_loop_manager.is_running,
    )
