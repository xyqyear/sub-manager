from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=settings.sql_echo)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_new_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def _get_alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    ini_path = backend_dir / "alembic.ini"
    cfg = Config(str(ini_path))
    sync_url = settings.database_url.replace("+aiosqlite", "")
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


async def init_db() -> None:
    async with engine.begin() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        has_tables = bool(table_names)
        has_alembic = "alembic_version" in table_names

    await engine.dispose()

    cfg = _get_alembic_config()

    if not has_tables:
        logger.info("Fresh database — creating all tables and stamping head")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()
        await asyncio.to_thread(command.stamp, cfg, "head")
    elif not has_alembic:
        logger.info("Existing database without Alembic — stamping 001 then upgrading")
        await asyncio.to_thread(command.stamp, cfg, "001")
        await asyncio.to_thread(command.upgrade, cfg, "head")
    else:
        logger.info("Running Alembic upgrade to head")
        await asyncio.to_thread(command.upgrade, cfg, "head")
