from __future__ import annotations

import copy
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import yaml

from app.config import settings
from app.models import SubscriptionSource
from app.schemas.subscriptions import SubscriptionCreate, SubscriptionUpdate
from app.services.common import ServiceError, next_refresh_time, parse_subscription_userinfo, utc_now


def _normalize_interval(interval_sec: int) -> int:
    return max(settings.min_refresh_interval_sec, min(settings.max_refresh_interval_sec, interval_sec))


def _validate_manual_proxy_text(proxy_yaml_object_text: str | None) -> list[dict[str, Any]]:
    if not proxy_yaml_object_text:
        raise ServiceError("manual mode requires proxy_yaml_object_text", 422)

    try:
        parsed = yaml.safe_load(proxy_yaml_object_text)
    except yaml.YAMLError as exc:
        raise ServiceError(f"invalid proxy yaml: {exc}", 422) from exc

    if not isinstance(parsed, list):
        raise ServiceError("manual proxy must be a YAML list of proxy objects", 422)

    for i, item in enumerate(parsed):
        if not isinstance(item, dict) or not item:
            raise ServiceError(f"manual proxy list item {i} must be a non-empty object", 422)

    return parsed


def _parse_remote_subscription_payload(content: str) -> list[dict[str, Any]]:
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ServiceError(f"subscription YAML parse failed: {exc}", 422) from exc

    if not isinstance(parsed, dict):
        raise ServiceError("subscription response must be a YAML object", 422)

    proxies = parsed.get("proxies")
    if not isinstance(proxies, list):
        raise ServiceError("subscription missing proxies list", 422)

    normalized: list[dict[str, Any]] = []
    for item in proxies:
        if isinstance(item, dict):
            normalized.append(copy.deepcopy(item))
    return normalized


async def _assert_unique_name(db: AsyncSession, name: str, exclude_id: str | None = None) -> None:
    query = select(SubscriptionSource).where(SubscriptionSource.name == name)
    if exclude_id:
        query = query.where(SubscriptionSource.id != exclude_id)
    result = await db.execute(query)
    found = result.scalars().first()
    if found:
        raise ServiceError(f"subscription name already exists: {name}", 409)


async def create_subscription(db: AsyncSession, payload: SubscriptionCreate) -> SubscriptionSource:
    await _assert_unique_name(db, payload.name)

    mode = payload.mode
    update_interval_sec = _normalize_interval(payload.update_interval_sec)
    now = utc_now()

    source = SubscriptionSource(
        name=payload.name,
        mode=mode,
        enabled=payload.enabled,
        remote_url=payload.remote_url,
        remote_auth_header=payload.remote_auth_header,
        auto_update=payload.auto_update,
        update_interval_sec=update_interval_sec,
        last_status="never",
    )

    if mode == "remote":
        if not payload.remote_url:
            raise ServiceError("remote mode requires remote_url", 422)
        source.next_refresh_at = next_refresh_time(update_interval_sec) if payload.auto_update else None
    else:
        proxy_list = _validate_manual_proxy_text(payload.proxy_yaml_object_text)
        source.cached_proxies_json = proxy_list
        source.cached_raw_yaml = yaml.safe_dump(
            {"proxies": proxy_list},
            allow_unicode=True,
            sort_keys=False,
        )
        source.last_refresh_at = now
        source.last_status = "ok"
        source.next_refresh_at = None

    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def update_subscription(
    db: AsyncSession,
    source: SubscriptionSource,
    payload: SubscriptionUpdate,
) -> SubscriptionSource:
    if payload.name is not None and payload.name != source.name:
        await _assert_unique_name(db, payload.name, exclude_id=source.id)
        source.name = payload.name

    if payload.enabled is not None:
        source.enabled = payload.enabled

    if source.mode == "remote":
        if payload.remote_url is not None:
            source.remote_url = payload.remote_url
        if payload.remote_auth_header is not None:
            source.remote_auth_header = payload.remote_auth_header
        if payload.auto_update is not None:
            source.auto_update = payload.auto_update
        if payload.update_interval_sec is not None:
            source.update_interval_sec = _normalize_interval(payload.update_interval_sec)
        if source.auto_update:
            source.next_refresh_at = next_refresh_time(source.update_interval_sec)
        else:
            source.next_refresh_at = None
    else:
        if payload.proxy_yaml_object_text is not None:
            proxy_list = _validate_manual_proxy_text(payload.proxy_yaml_object_text)
            source.cached_proxies_json = proxy_list
            source.cached_raw_yaml = yaml.safe_dump(
                {"proxies": proxy_list},
                allow_unicode=True,
                sort_keys=False,
            )
            source.last_status = "ok"
            source.last_error = None
            source.last_refresh_at = utc_now()

    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def refresh_remote_subscription(db: AsyncSession, source: SubscriptionSource) -> SubscriptionSource:
    if source.mode != "remote":
        source.last_status = "ok"
        source.last_error = None
        source.last_refresh_at = utc_now()
        db.add(source)
        await db.commit()
        await db.refresh(source)
        return source

    if not source.remote_url:
        raise ServiceError("remote subscription has no remote_url", 422)

    headers = {"User-Agent": "mihomo/1.18.3"}
    if source.remote_auth_header:
        headers["Authorization"] = source.remote_auth_header

    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_sec,
            follow_redirects=True,
        ) as client:
            response = await client.get(source.remote_url, headers=headers)

        if response.status_code < 200 or response.status_code >= 300:
            raise ServiceError(
                f"subscription request failed with status {response.status_code}",
                502,
            )

        proxies = _parse_remote_subscription_payload(response.text)

        source.cached_raw_yaml = response.text
        source.cached_proxies_json = proxies
        source.subscription_userinfo_raw = response.headers.get("subscription-userinfo")
        source.subscription_userinfo_json = parse_subscription_userinfo(
            source.subscription_userinfo_raw
        )
        source.last_status = "ok"
        source.last_error = None
        source.last_refresh_at = utc_now()
        source.next_refresh_at = (
            next_refresh_time(source.update_interval_sec) if source.auto_update else None
        )

    except ServiceError as exc:
        source.last_status = "error"
        source.last_error = exc.message
        source.next_refresh_at = (
            next_refresh_time(source.update_interval_sec) if source.auto_update else None
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
        raise
    except Exception as exc:
        source.last_status = "error"
        source.last_error = f"subscription refresh failed: {exc}"
        source.next_refresh_at = (
            next_refresh_time(source.update_interval_sec) if source.auto_update else None
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
        raise ServiceError(source.last_error or "subscription refresh failed", 502) from exc

    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def get_subscription_or_404(db: AsyncSession, subscription_id: str) -> SubscriptionSource:
    source = await db.get(SubscriptionSource, subscription_id)
    if source is None:
        raise ServiceError("subscription not found", 404)
    return source


async def list_subscriptions(db: AsyncSession) -> list[SubscriptionSource]:
    result = await db.execute(select(SubscriptionSource).order_by(SubscriptionSource.created_at.desc()))
    return list(result.scalars().all())


async def delete_subscription(db: AsyncSession, source: SubscriptionSource) -> None:
    await db.delete(source)
    await db.commit()


async def get_due_subscription_ids(db: AsyncSession) -> list[str]:
    now = utc_now()
    result = await db.execute(
        select(SubscriptionSource.id).where(
            SubscriptionSource.mode == "remote",
            SubscriptionSource.auto_update.is_(True),
            SubscriptionSource.enabled.is_(True),
            SubscriptionSource.next_refresh_at.is_not(None),
            SubscriptionSource.next_refresh_at <= now,
        )
    )
    return [item for item in result.scalars().all()]
