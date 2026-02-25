from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MainConfig, RouteTemplate, RuleSource


async def check_name_exists(
    db: AsyncSession, name: str, exclude_id: str | None = None
) -> bool:
    query = select(RouteTemplate).where(RouteTemplate.name == name)
    if exclude_id:
        query = query.where(RouteTemplate.id != exclude_id)
    found = await db.scalars(query)
    return found.first() is not None


async def check_rule_source_ids_exist(
    db: AsyncSession, ids: set[str]
) -> set[str]:
    if not ids:
        return set()
    result = await db.scalars(select(RuleSource.id).where(RuleSource.id.in_(ids)))
    return set(result.all())


async def get_max_position(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(RouteTemplate.position), -1))
    )
    return result.scalar_one()


async def save(db: AsyncSession, template: RouteTemplate) -> RouteTemplate:
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def get_by_id(db: AsyncSession, template_id: str) -> RouteTemplate | None:
    return await db.get(RouteTemplate, template_id)


async def list_all_ordered(db: AsyncSession) -> list[RouteTemplate]:
    result = await db.scalars(
        select(RouteTemplate).order_by(
            RouteTemplate.position.asc(), RouteTemplate.created_at.desc()
        )
    )
    return list(result.all())


async def has_referencing_main_configs(db: AsyncSession, template_id: str) -> bool:
    result = await db.scalars(
        select(MainConfig.id)
        .where(MainConfig.route_template_id == template_id)
        .limit(1)
    )
    return result.first() is not None


async def delete(db: AsyncSession, template: RouteTemplate) -> None:
    await db.delete(template)
    await db.commit()


async def bulk_update_positions(
    db: AsyncSession, items: list[tuple[str, int]]
) -> None:
    for item_id, position in items:
        await db.execute(
            update(RouteTemplate)
            .where(RouteTemplate.id == item_id)
            .values(position=position)
        )
    await db.commit()
