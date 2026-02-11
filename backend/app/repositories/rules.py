from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RuleSource


class RuleRepository:
    @staticmethod
    async def list_all(db: AsyncSession) -> list[RuleSource]:
        result = await db.execute(select(RuleSource).order_by(RuleSource.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, rule_id: str) -> RuleSource | None:
        return await db.get(RuleSource, rule_id)

    @staticmethod
    async def get_many(db: AsyncSession, rule_ids: list[str]) -> list[RuleSource]:
        if not rule_ids:
            return []
        result = await db.execute(select(RuleSource).where(RuleSource.id.in_(rule_ids)))
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, rule: RuleSource) -> RuleSource:
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def save(db: AsyncSession, rule: RuleSource) -> RuleSource:
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def delete(db: AsyncSession, rule_id: str) -> None:
        await db.execute(delete(RuleSource).where(RuleSource.id == rule_id))
        await db.commit()
