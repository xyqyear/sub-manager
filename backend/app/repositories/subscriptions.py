from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SubscriptionSource


class SubscriptionRepository:
    @staticmethod
    async def list_all(db: AsyncSession) -> list[SubscriptionSource]:
        result = await db.execute(select(SubscriptionSource).order_by(SubscriptionSource.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, subscription_id: str) -> SubscriptionSource | None:
        return await db.get(SubscriptionSource, subscription_id)

    @staticmethod
    async def get_many(db: AsyncSession, subscription_ids: list[str]) -> list[SubscriptionSource]:
        if not subscription_ids:
            return []
        result = await db.execute(
            select(SubscriptionSource).where(SubscriptionSource.id.in_(subscription_ids))
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, subscription: SubscriptionSource) -> SubscriptionSource:
        db.add(subscription)
        await db.commit()
        await db.refresh(subscription)
        return subscription

    @staticmethod
    async def save(db: AsyncSession, subscription: SubscriptionSource) -> SubscriptionSource:
        db.add(subscription)
        await db.commit()
        await db.refresh(subscription)
        return subscription

    @staticmethod
    async def delete(db: AsyncSession, subscription_id: str) -> None:
        await db.execute(delete(SubscriptionSource).where(SubscriptionSource.id == subscription_id))
        await db.commit()
