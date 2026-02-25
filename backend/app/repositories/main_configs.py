from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MainConfig, SubscriptionSource


async def check_name_exists(
    db: AsyncSession, name: str, exclude_id: str | None = None
) -> bool:
    query = select(MainConfig).where(MainConfig.name == name)
    if exclude_id:
        query = query.where(MainConfig.id != exclude_id)
    found = await db.scalars(query)
    return found.first() is not None


async def check_subscription_ids_exist(
    db: AsyncSession, ids: set[str]
) -> set[str]:
    if not ids:
        return set()
    result = await db.scalars(
        select(SubscriptionSource.id).where(SubscriptionSource.id.in_(ids))
    )
    return set(result.all())


async def get_max_position(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(MainConfig.position), -1))
    )
    return result.scalar_one()


async def save(db: AsyncSession, config: MainConfig) -> MainConfig:
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def get_by_id(db: AsyncSession, config_id: str) -> MainConfig | None:
    return await db.get(MainConfig, config_id)


async def list_all_ordered(db: AsyncSession) -> list[MainConfig]:
    result = await db.scalars(
        select(MainConfig).order_by(
            MainConfig.position.asc(), MainConfig.created_at.desc()
        )
    )
    return list(result.all())


async def delete(db: AsyncSession, config: MainConfig) -> None:
    await db.delete(config)
    await db.commit()


async def bulk_update_positions(
    db: AsyncSession, items: list[tuple[str, int]]
) -> None:
    for item_id, position in items:
        await db.execute(
            update(MainConfig)
            .where(MainConfig.id == item_id)
            .values(position=position)
        )
    await db.commit()
