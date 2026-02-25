from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SubscriptionSource
from app.services.common import utc_now


async def check_name_exists(
    db: AsyncSession, name: str, exclude_id: str | None = None
) -> bool:
    query = select(SubscriptionSource).where(SubscriptionSource.name == name)
    if exclude_id:
        query = query.where(SubscriptionSource.id != exclude_id)
    found = await db.scalars(query)
    return found.first() is not None


async def get_max_position(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(SubscriptionSource.position), -1))
    )
    return result.scalar_one()


async def save(db: AsyncSession, source: SubscriptionSource) -> SubscriptionSource:
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def get_by_id(db: AsyncSession, subscription_id: str) -> SubscriptionSource | None:
    return await db.get(SubscriptionSource, subscription_id)


async def list_all_ordered(db: AsyncSession) -> list[SubscriptionSource]:
    result = await db.scalars(
        select(SubscriptionSource).order_by(
            SubscriptionSource.position.asc(), SubscriptionSource.created_at.desc()
        )
    )
    return list(result.all())


async def list_summary(db: AsyncSession) -> list[dict[str, Any]]:
    S = SubscriptionSource
    cols = [
        S.id, S.name, S.mode, S.enabled,
        S.remote_url, S.remote_auth_header,
        S.auto_update, S.update_interval_sec,
        S.next_refresh_at, S.last_refresh_at,
        S.last_status, S.last_error,
        S.subscription_userinfo_raw, S.subscription_userinfo_json,
        func.json_array_length(S.cached_proxies_json).label("cached_proxies_count"),
        S.created_at, S.updated_at, S.position,
    ]
    result = await db.execute(select(*cols).order_by(S.position.asc(), S.created_at.desc()))
    return [row._asdict() for row in result.all()]


async def delete(db: AsyncSession, source: SubscriptionSource) -> None:
    await db.delete(source)
    await db.commit()


async def get_due_ids(db: AsyncSession) -> list[str]:
    now = utc_now()
    result = await db.scalars(
        select(SubscriptionSource.id).where(
            SubscriptionSource.mode == "remote",
            SubscriptionSource.auto_update.is_(True),
            SubscriptionSource.enabled.is_(True),
            SubscriptionSource.next_refresh_at.is_not(None),
            SubscriptionSource.next_refresh_at <= now,
        )
    )
    return list(result.all())


async def bulk_update_positions(
    db: AsyncSession, items: list[tuple[str, int]]
) -> None:
    for item_id, position in items:
        await db.execute(
            update(SubscriptionSource)
            .where(SubscriptionSource.id == item_id)
            .values(position=position)
        )
    await db.commit()


async def fetch_by_ids(
    db: AsyncSession, ids: list[str]
) -> dict[str, SubscriptionSource]:
    if not ids:
        return {}
    result = await db.scalars(
        select(SubscriptionSource).where(SubscriptionSource.id.in_(ids))
    )
    return {item.id: item for item in result.all()}
