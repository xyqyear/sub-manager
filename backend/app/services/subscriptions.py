from __future__ import annotations

import copy
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import SubscriptionSource
from app.repositories import subscriptions as subscription_repo
from app.schemas.reorder import ReorderRequest
from app.schemas.subscriptions import SubscriptionCreate, SubscriptionUpdate
from app.services.common import (
    ServiceError,
    next_refresh_time,
    parse_subscription_userinfo,
    utc_now,
)
from app.services.subscription_uri import parse_uri_subscription_payload
from app.yaml import YAMLError, yaml_dump, yaml_load


def _normalize_interval(interval_sec: int) -> int:
    return max(settings.min_refresh_interval_sec, min(settings.max_refresh_interval_sec, interval_sec))


def _validate_manual_proxy_text(proxy_yaml_object_text: str | None) -> list[dict[str, Any]]:
    if not proxy_yaml_object_text:
        raise ServiceError("manual mode requires proxy_yaml_object_text", 422)

    try:
        parsed = yaml_load(proxy_yaml_object_text)
    except YAMLError as exc:
        raise ServiceError(f"invalid proxy yaml: {exc}", 422) from exc

    if not isinstance(parsed, list):
        raise ServiceError("manual proxy must be a YAML list of proxy objects", 422)

    for i, item in enumerate(parsed):
        if not isinstance(item, dict) or not item:
            raise ServiceError(f"manual proxy list item {i} must be a non-empty object", 422)

    return parsed


def _parse_remote_subscription_payload(content: str) -> list[dict[str, Any]]:
    try:
        parsed = yaml_load(content)
    except YAMLError as exc:
        yaml_error = str(exc)
    else:
        if isinstance(parsed, dict):
            proxies = parsed.get("proxies")
            if isinstance(proxies, list):
                normalized: list[dict[str, Any]] = []
                for item in proxies:
                    if isinstance(item, dict):
                        normalized.append(copy.deepcopy(item))
                return normalized
            yaml_error = "subscription missing proxies list"
        else:
            yaml_error = "subscription response must be a YAML object"

    try:
        return parse_uri_subscription_payload(content)
    except ValueError as exc:
        raise ServiceError(f"subscription parse failed: {yaml_error}; {exc}", 422) from exc


async def create_subscription(db: AsyncSession, payload: SubscriptionCreate) -> SubscriptionSource:
    if await subscription_repo.check_name_exists(db, payload.name):
        raise ServiceError(f"subscription name already exists: {payload.name}", 409)

    mode = payload.mode
    update_interval_sec = _normalize_interval(payload.update_interval_sec)
    now = utc_now()

    max_pos = await subscription_repo.get_max_position(db)

    source = SubscriptionSource(
        name=payload.name,
        mode=mode,
        enabled=payload.enabled,
        remote_url=payload.remote_url,
        remote_auth_header=payload.remote_auth_header,
        auto_update=payload.auto_update,
        update_interval_sec=update_interval_sec,
        last_status="never",
        position=max_pos + 1,
    )

    if mode == "remote":
        if not payload.remote_url:
            raise ServiceError("remote mode requires remote_url", 422)
        source.next_refresh_at = next_refresh_time(update_interval_sec) if payload.auto_update else None
    else:
        proxy_list = _validate_manual_proxy_text(payload.proxy_yaml_object_text)
        source.cached_proxies_json = proxy_list
        source.cached_raw_yaml = yaml_dump({"proxies": proxy_list})
        source.last_refresh_at = now
        source.last_status = "ok"
        source.next_refresh_at = None

    return await subscription_repo.save(db, source)


async def update_subscription(
    db: AsyncSession,
    source: SubscriptionSource,
    payload: SubscriptionUpdate,
) -> SubscriptionSource:
    if payload.name is not None and payload.name != source.name:
        if await subscription_repo.check_name_exists(db, payload.name, exclude_id=source.id):
            raise ServiceError(f"subscription name already exists: {payload.name}", 409)
        source.name = payload.name

    if payload.enabled is not None:
        source.enabled = payload.enabled

    effective_mode = payload.mode if payload.mode is not None else source.mode
    mode_changed = payload.mode is not None and payload.mode != source.mode

    if mode_changed:
        source.mode = effective_mode

    if effective_mode == "remote":
        if mode_changed and not (payload.remote_url or source.remote_url):
            raise ServiceError("remote mode requires remote_url", 422)
        if payload.remote_url is not None:
            source.remote_url = payload.remote_url
        if payload.remote_auth_header is not None:
            source.remote_auth_header = payload.remote_auth_header
        if payload.auto_update is not None:
            source.auto_update = payload.auto_update
        if payload.update_interval_sec is not None:
            source.update_interval_sec = _normalize_interval(payload.update_interval_sec)
        source.next_refresh_at = (
            next_refresh_time(source.update_interval_sec) if source.auto_update else None
        )
    else:
        if mode_changed or payload.proxy_yaml_object_text is not None:
            proxy_list = _validate_manual_proxy_text(payload.proxy_yaml_object_text)
            source.cached_proxies_json = proxy_list
            source.cached_raw_yaml = yaml_dump({"proxies": proxy_list})
            source.last_status = "ok"
            source.last_error = None
            source.last_refresh_at = utc_now()
        if mode_changed:
            source.subscription_userinfo_raw = None
            source.subscription_userinfo_json = None
            source.auto_update = False
            source.next_refresh_at = None

    return await subscription_repo.save(db, source)


async def refresh_remote_subscription(db: AsyncSession, source: SubscriptionSource) -> SubscriptionSource:
    if source.mode != "remote":
        source.last_status = "ok"
        source.last_error = None
        source.last_refresh_at = utc_now()
        return await subscription_repo.save(db, source)

    if not source.remote_url:
        raise ServiceError("remote subscription has no remote_url", 422)

    headers = {"User-Agent": "mihomo.party/v1.8.9 (clash.meta)"}
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
        await subscription_repo.save(db, source)
        raise
    except Exception as exc:
        source.last_status = "error"
        source.last_error = f"subscription refresh failed: {exc}"
        source.next_refresh_at = (
            next_refresh_time(source.update_interval_sec) if source.auto_update else None
        )
        await subscription_repo.save(db, source)
        raise ServiceError(source.last_error or "subscription refresh failed", 502) from exc

    return await subscription_repo.save(db, source)


async def get_subscription_or_404(db: AsyncSession, subscription_id: str) -> SubscriptionSource:
    source = await subscription_repo.get_by_id(db, subscription_id)
    if source is None:
        raise ServiceError("subscription not found", 404)
    return source


async def list_subscriptions(db: AsyncSession) -> list[SubscriptionSource]:
    return await subscription_repo.list_all_ordered(db)


async def list_subscriptions_summary(db: AsyncSession) -> list[dict[str, Any]]:
    return await subscription_repo.list_summary(db)


async def delete_subscription(db: AsyncSession, source: SubscriptionSource) -> None:
    await subscription_repo.delete(db, source)


async def get_due_subscription_ids(db: AsyncSession) -> list[str]:
    return await subscription_repo.get_due_ids(db)


async def reorder_subscriptions(db: AsyncSession, payload: ReorderRequest) -> None:
    await subscription_repo.bulk_update_positions(
        db, [(item.id, item.position) for item in payload.items]
    )
