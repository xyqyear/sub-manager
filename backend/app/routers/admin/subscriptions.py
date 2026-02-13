from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_token
from app.db.database import get_db
from app.schemas.subscriptions import (
    SubscriptionCreate,
    SubscriptionRead,
    SubscriptionRefreshResponse,
    SubscriptionUpdate,
)
from app.services.common import ServiceError, to_http_error
from app.services.refresh_loop import refresh_loop_manager
from app.services.subscriptions import (
    create_subscription,
    delete_subscription,
    get_subscription_or_404,
    list_subscriptions,
    refresh_remote_subscription,
    update_subscription,
)

router = APIRouter(
    prefix="/admin/subscriptions",
    tags=["admin-subscriptions"],
    dependencies=[Depends(require_admin_token)],
)

@router.get("", response_model=list[SubscriptionRead])
async def get_subscriptions(db: AsyncSession = Depends(get_db)) -> list[SubscriptionRead]:
    rows = await list_subscriptions(db)
    return [SubscriptionRead.model_validate(row) for row in rows]


@router.post("", response_model=SubscriptionRead)
async def create_subscription_endpoint(
    payload: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionRead:
    try:
        row = await create_subscription(db, payload)
        return SubscriptionRead.model_validate(row)
    except ServiceError as exc:
        raise to_http_error(exc)


@router.put("/{subscription_id}", response_model=SubscriptionRead)
async def update_subscription_endpoint(
    subscription_id: str,
    payload: SubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionRead:
    try:
        source = await get_subscription_or_404(db, subscription_id)
        source = await update_subscription(db, source, payload)
        return SubscriptionRead.model_validate(source)
    except ServiceError as exc:
        raise to_http_error(exc)


@router.post("/{subscription_id}/refresh", response_model=SubscriptionRefreshResponse)
async def refresh_subscription_endpoint(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionRefreshResponse:
    try:
        source = await get_subscription_or_404(db, subscription_id)
        if source.mode == "remote":
            source = await refresh_remote_subscription(db, source)
        else:
            source = await update_subscription(db, source, SubscriptionUpdate())

        return SubscriptionRefreshResponse(
            id=source.id,
            status=source.last_status,
            detail=source.last_error or "ok",
        )
    except ServiceError as exc:
        raise to_http_error(exc)


@router.post("/{subscription_id}/refresh-async", response_model=SubscriptionRefreshResponse)
async def refresh_subscription_async_endpoint(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionRefreshResponse:
    try:
        source = await get_subscription_or_404(db, subscription_id)
        await refresh_loop_manager.enqueue_subscription_refresh(source.id)
        return SubscriptionRefreshResponse(
            id=source.id,
            status="queued",
            detail="refresh queued",
        )
    except ServiceError as exc:
        raise to_http_error(exc)


@router.delete("/{subscription_id}")
async def delete_subscription_endpoint(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    try:
        source = await get_subscription_or_404(db, subscription_id)
        await delete_subscription(db, source)
        return {"status": "ok"}
    except ServiceError as exc:
        raise to_http_error(exc)
