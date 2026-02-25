from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RuleSource
from app.services.common import utc_now


async def check_name_exists(
    db: AsyncSession, name: str, exclude_id: str | None = None
) -> bool:
    query = select(RuleSource).where(RuleSource.name == name)
    if exclude_id:
        query = query.where(RuleSource.id != exclude_id)
    found = await db.scalars(query)
    return found.first() is not None


async def get_max_position(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(RuleSource.position), -1))
    )
    return result.scalar_one()


async def save(db: AsyncSession, source: RuleSource) -> RuleSource:
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def get_by_id(db: AsyncSession, rule_id: str) -> RuleSource | None:
    return await db.get(RuleSource, rule_id)


async def list_all_ordered(db: AsyncSession) -> list[RuleSource]:
    result = await db.scalars(
        select(RuleSource).order_by(
            RuleSource.position.asc(), RuleSource.created_at.desc()
        )
    )
    return list(result.all())


async def list_summary(db: AsyncSession) -> list[dict[str, Any]]:
    R = RuleSource
    cols = [
        R.id, R.name, R.mode, R.behavior, R.enabled,
        R.remote_url, R.auto_update, R.update_interval_sec,
        R.next_refresh_at, R.last_refresh_at,
        R.last_status, R.last_error,
        func.json_array_length(R.cached_payload_lines_json).label(
            "cached_payload_lines_count"
        ),
        R.created_at, R.updated_at, R.position,
    ]
    result = await db.execute(
        select(*cols).order_by(R.position.asc(), R.created_at.desc())
    )
    return [row._asdict() for row in result.all()]


async def delete(db: AsyncSession, source: RuleSource) -> None:
    await db.delete(source)
    await db.commit()


async def get_due_ids(db: AsyncSession) -> list[str]:
    now = utc_now()
    result = await db.scalars(
        select(RuleSource.id).where(
            RuleSource.mode == "remote",
            RuleSource.auto_update.is_(True),
            RuleSource.enabled.is_(True),
            RuleSource.next_refresh_at.is_not(None),
            RuleSource.next_refresh_at <= now,
        )
    )
    return list(result.all())


async def bulk_update_positions(
    db: AsyncSession, items: list[tuple[str, int]]
) -> None:
    for item_id, position in items:
        await db.execute(
            update(RuleSource)
            .where(RuleSource.id == item_id)
            .values(position=position)
        )
    await db.commit()


async def fetch_by_ids(
    db: AsyncSession, ids: list[str]
) -> dict[str, RuleSource]:
    if not ids:
        return {}
    result = await db.scalars(
        select(RuleSource).where(RuleSource.id.in_(ids))
    )
    return {item.id: item for item in result.all()}
