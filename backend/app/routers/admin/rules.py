from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_token
from app.db.database import get_db
from app.schemas.rules import RuleCreate, RuleRead, RuleRefreshResponse, RuleUpdate
from app.services.common import ServiceError, to_http_error
from app.services.refresh_loop import refresh_loop_manager
from app.services.rules import (
    create_rule,
    delete_rule,
    get_rule_or_404,
    list_rules,
    refresh_remote_rule,
    update_rule,
)

router = APIRouter(
    prefix="/admin/rules",
    tags=["admin-rules"],
    dependencies=[Depends(require_admin_token)],
)

@router.get("", response_model=list[RuleRead])
async def get_rules(db: AsyncSession = Depends(get_db)) -> list[RuleRead]:
    rows = await list_rules(db)
    return [RuleRead.model_validate(row) for row in rows]


@router.post("", response_model=RuleRead)
async def create_rule_endpoint(
    payload: RuleCreate,
    db: AsyncSession = Depends(get_db),
) -> RuleRead:
    try:
        row = await create_rule(db, payload)
        return RuleRead.model_validate(row)
    except ServiceError as exc:
        raise to_http_error(exc)


@router.put("/{rule_id}", response_model=RuleRead)
async def update_rule_endpoint(
    rule_id: str,
    payload: RuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> RuleRead:
    try:
        row = await get_rule_or_404(db, rule_id)
        row = await update_rule(db, row, payload)
        return RuleRead.model_validate(row)
    except ServiceError as exc:
        raise to_http_error(exc)


@router.post("/{rule_id}/refresh", response_model=RuleRefreshResponse)
async def refresh_rule_endpoint(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> RuleRefreshResponse:
    try:
        row = await get_rule_or_404(db, rule_id)
        if row.mode == "remote":
            row = await refresh_remote_rule(db, row)
        else:
            row = await update_rule(db, row, RuleUpdate())
        return RuleRefreshResponse(id=row.id, status=row.last_status, detail=row.last_error or "ok")
    except ServiceError as exc:
        raise to_http_error(exc)


@router.post("/{rule_id}/refresh-async", response_model=RuleRefreshResponse)
async def refresh_rule_async_endpoint(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> RuleRefreshResponse:
    try:
        row = await get_rule_or_404(db, rule_id)
        await refresh_loop_manager.enqueue_rule_refresh(row.id)
        return RuleRefreshResponse(id=row.id, status="queued", detail="refresh queued")
    except ServiceError as exc:
        raise to_http_error(exc)


@router.delete("/{rule_id}")
async def delete_rule_endpoint(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    try:
        row = await get_rule_or_404(db, rule_id)
        await delete_rule(db, row)
        return {"status": "ok"}
    except ServiceError as exc:
        raise to_http_error(exc)
