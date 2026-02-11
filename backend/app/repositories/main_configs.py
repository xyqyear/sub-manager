from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MainConfig


class MainConfigRepository:
    @staticmethod
    async def list_all(db: AsyncSession) -> list[MainConfig]:
        result = await db.execute(select(MainConfig).order_by(MainConfig.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, config_id: str) -> MainConfig | None:
        return await db.get(MainConfig, config_id)

    @staticmethod
    async def create(db: AsyncSession, config: MainConfig) -> MainConfig:
        db.add(config)
        await db.commit()
        await db.refresh(config)
        return config

    @staticmethod
    async def save(db: AsyncSession, config: MainConfig) -> MainConfig:
        db.add(config)
        await db.commit()
        await db.refresh(config)
        return config

    @staticmethod
    async def delete(db: AsyncSession, config_id: str) -> None:
        await db.execute(delete(MainConfig).where(MainConfig.id == config_id))
        await db.commit()
