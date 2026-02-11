from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.services.rules import get_due_rule_ids, get_rule_or_404, refresh_remote_rule
from app.services.subscriptions import (
    get_due_subscription_ids,
    get_subscription_or_404,
    refresh_remote_subscription,
)

logger = logging.getLogger("sub_manager.refresh_loop")


class RefreshLoopManager:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._subscription_inflight: set[str] = set()
        self._rule_inflight: set[str] = set()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="refresh-loop")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def enqueue_subscription_refresh(self, subscription_id: str) -> None:
        if subscription_id in self._subscription_inflight:
            return
        self._subscription_inflight.add(subscription_id)
        asyncio.create_task(self._refresh_subscription(subscription_id))

    async def enqueue_rule_refresh(self, rule_id: str) -> None:
        if rule_id in self._rule_inflight:
            return
        self._rule_inflight.add(rule_id)
        asyncio.create_task(self._refresh_rule(rule_id))

    async def _refresh_subscription(self, subscription_id: str) -> None:
        try:
            async with AsyncSessionLocal() as db:
                source = await get_subscription_or_404(db, subscription_id)
                await refresh_remote_subscription(db, source)
                logger.info("subscription refreshed", extra={"subscription_id": subscription_id})
        except Exception as exc:
            logger.warning(
                "subscription refresh failed: %s",
                exc,
                extra={"subscription_id": subscription_id},
            )
        finally:
            self._subscription_inflight.discard(subscription_id)

    async def _refresh_rule(self, rule_id: str) -> None:
        try:
            async with AsyncSessionLocal() as db:
                source = await get_rule_or_404(db, rule_id)
                await refresh_remote_rule(db, source)
                logger.info("rule refreshed", extra={"rule_id": rule_id})
        except Exception as exc:
            logger.warning("rule refresh failed: %s", exc, extra={"rule_id": rule_id})
        finally:
            self._rule_inflight.discard(rule_id)

    async def _run_loop(self) -> None:
        logger.info("refresh loop started")
        while not self._stop_event.is_set():
            try:
                async with AsyncSessionLocal() as db:
                    due_subscription_ids = await get_due_subscription_ids(db)
                    due_rule_ids = await get_due_rule_ids(db)

                for subscription_id in due_subscription_ids:
                    await self.enqueue_subscription_refresh(subscription_id)

                for rule_id in due_rule_ids:
                    await self.enqueue_rule_refresh(rule_id)

            except Exception as exc:
                logger.warning("refresh loop iteration failed: %s", exc)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=settings.refresh_loop_tick_sec,
                )
            except asyncio.TimeoutError:
                continue

        logger.info("refresh loop stopped")


refresh_loop_manager = RefreshLoopManager()
