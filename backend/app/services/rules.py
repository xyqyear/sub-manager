from __future__ import annotations

from ipaddress import ip_network
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import RuleSource
from app.repositories import rules as rule_repo
from app.schemas.common import RuleBehavior
from app.schemas.reorder import ReorderRequest
from app.schemas.rules import RuleCreate, RuleUpdate
from app.services.common import ServiceError, next_refresh_time, utc_now
from app.yaml import YAMLError, yaml_load


def _normalize_interval(interval_sec: int) -> int:
    return max(
        settings.min_refresh_interval_sec,
        min(settings.max_refresh_interval_sec, interval_sec),
    )


def validate_rule_payload_lines(behavior: RuleBehavior, lines: list[str]) -> list[str]:
    normalized = [line.strip() for line in lines if line.strip()]
    if not normalized:
        raise ServiceError("payload_lines cannot be empty", 422)

    if behavior == "ipcidr":
        for line in normalized:
            try:
                ip_network(line, strict=False)
            except ValueError as exc:
                raise ServiceError(f"invalid ipcidr entry: {line}", 422) from exc

    return normalized


def _parse_rule_payload_from_yaml(content: str, behavior: RuleBehavior) -> list[str]:
    try:
        parsed = yaml_load(content)
    except YAMLError as exc:
        raise ServiceError(f"rule YAML parse failed: {exc}", 422) from exc

    if not isinstance(parsed, dict):
        raise ServiceError("rule response must be YAML object", 422)

    payload = parsed.get("payload")
    if not isinstance(payload, list):
        raise ServiceError("rule payload must be list", 422)

    lines: list[str] = []
    for item in payload:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                lines.append(stripped)

    return validate_rule_payload_lines(behavior, lines)


async def create_rule(db: AsyncSession, payload: RuleCreate) -> RuleSource:
    if await rule_repo.check_name_exists(db, payload.name):
        raise ServiceError(f"rule name already exists: {payload.name}", 409)

    interval = _normalize_interval(payload.update_interval_sec)
    max_pos = await rule_repo.get_max_position(db)
    source = RuleSource(
        name=payload.name,
        mode=payload.mode,
        behavior=payload.behavior,
        enabled=payload.enabled,
        remote_url=payload.remote_url,
        auto_update=payload.auto_update,
        update_interval_sec=interval,
        position=max_pos + 1,
    )

    if payload.mode == "remote":
        if not payload.remote_url:
            raise ServiceError("remote mode requires remote_url", 422)
        source.next_refresh_at = (
            next_refresh_time(interval) if payload.auto_update else None
        )
    else:
        if payload.payload_lines is None:
            raise ServiceError("manual mode requires payload_lines", 422)
        source.cached_payload_lines_json = validate_rule_payload_lines(
            payload.behavior,
            payload.payload_lines,
        )
        source.last_status = "ok"
        source.last_error = None
        source.last_refresh_at = utc_now()
        source.next_refresh_at = None

    return await rule_repo.save(db, source)


async def update_rule(
    db: AsyncSession, source: RuleSource, payload: RuleUpdate
) -> RuleSource:
    if payload.name is not None and payload.name != source.name:
        if await rule_repo.check_name_exists(db, payload.name, exclude_id=source.id):
            raise ServiceError(f"rule name already exists: {payload.name}", 409)
        source.name = payload.name

    if payload.enabled is not None:
        source.enabled = payload.enabled

    if payload.behavior is not None:
        source.behavior = payload.behavior

    effective_mode = payload.mode if payload.mode is not None else source.mode
    mode_changed = payload.mode is not None and payload.mode != source.mode

    if mode_changed:
        source.mode = effective_mode

    if effective_mode == "remote":
        if mode_changed and not (payload.remote_url or source.remote_url):
            raise ServiceError("remote mode requires remote_url", 422)
        if payload.remote_url is not None:
            source.remote_url = payload.remote_url
        if payload.auto_update is not None:
            source.auto_update = payload.auto_update
        if payload.update_interval_sec is not None:
            source.update_interval_sec = _normalize_interval(
                payload.update_interval_sec
            )
        source.next_refresh_at = (
            next_refresh_time(source.update_interval_sec)
            if source.auto_update
            else None
        )
    else:
        if mode_changed and payload.payload_lines is None:
            raise ServiceError("manual mode requires payload_lines", 422)
        if mode_changed or payload.payload_lines is not None:
            source.cached_payload_lines_json = validate_rule_payload_lines(
                source.behavior,
                payload.payload_lines or [],
            )
            source.last_status = "ok"
            source.last_error = None
            source.last_refresh_at = utc_now()
        if mode_changed:
            source.auto_update = False
            source.next_refresh_at = None

    return await rule_repo.save(db, source)


async def refresh_remote_rule(db: AsyncSession, source: RuleSource) -> RuleSource:
    if source.mode != "remote":
        source.last_status = "ok"
        source.last_error = None
        source.last_refresh_at = utc_now()
        return await rule_repo.save(db, source)

    if not source.remote_url:
        raise ServiceError("remote rule has no remote_url", 422)

    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_sec,
            follow_redirects=True,
        ) as client:
            response = await client.get(source.remote_url)

        if response.status_code < 200 or response.status_code >= 300:
            raise ServiceError(
                f"rule request failed with status {response.status_code}", 502
            )

        payload_lines = _parse_rule_payload_from_yaml(response.text, source.behavior)

        source.cached_payload_lines_json = payload_lines
        source.last_status = "ok"
        source.last_error = None
        source.last_refresh_at = utc_now()
        source.next_refresh_at = (
            next_refresh_time(source.update_interval_sec)
            if source.auto_update
            else None
        )

    except ServiceError as exc:
        source.last_status = "error"
        source.last_error = exc.message
        source.next_refresh_at = (
            next_refresh_time(source.update_interval_sec)
            if source.auto_update
            else None
        )
        await rule_repo.save(db, source)
        raise
    except Exception as exc:
        source.last_status = "error"
        source.last_error = f"rule refresh failed: {exc}"
        source.next_refresh_at = (
            next_refresh_time(source.update_interval_sec)
            if source.auto_update
            else None
        )
        await rule_repo.save(db, source)
        raise ServiceError(source.last_error or "", 502) from exc

    return await rule_repo.save(db, source)


async def get_rule_or_404(db: AsyncSession, rule_id: str) -> RuleSource:
    source = await rule_repo.get_by_id(db, rule_id)
    if source is None:
        raise ServiceError("rule not found", 404)
    return source


async def list_rules(db: AsyncSession) -> list[RuleSource]:
    return await rule_repo.list_all_ordered(db)


async def list_rules_summary(db: AsyncSession) -> list[dict[str, Any]]:
    return await rule_repo.list_summary(db)


async def delete_rule(db: AsyncSession, source: RuleSource) -> None:
    await rule_repo.delete(db, source)


async def get_due_rule_ids(db: AsyncSession) -> list[str]:
    return await rule_repo.get_due_ids(db)


async def reorder_rules(db: AsyncSession, payload: ReorderRequest) -> None:
    await rule_repo.bulk_update_positions(
        db, [(item.id, item.position) for item in payload.items]
    )
