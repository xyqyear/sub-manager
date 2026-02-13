from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import yaml

from app.config import settings
from app.models import (
    MainConfig,
    RuleSource,
    SubscriptionSource,
)
from app.schemas.configs import (
    BuilderPayload,
    FilteredGroupPreviewItem,
    FilteredGroupPreviewRequest,
    FilteredGroupPreviewResponse,
    FinalTargetType,
    MainConfigCreate,
    MainConfigUpdate,
)
from app.services.common import ServiceError
from app.services.generator import (
    FilteredRuleMatch,
    OrderedSource,
    build_proxy_pool_with_collision_names,
    match_filtered_rules_on_proxies,
)


async def _assert_unique_config_name(db: AsyncSession, name: str, exclude_id: str | None = None) -> None:
    query = select(MainConfig).where(MainConfig.name == name)
    if exclude_id:
        query = query.where(MainConfig.id != exclude_id)
    result = await db.execute(query)
    found = result.scalars().first()
    if found:
        raise ServiceError(f"main config name already exists: {name}", 409)


def validate_base_yaml(base_config_yaml: str) -> None:
    try:
        parsed = yaml.safe_load(base_config_yaml)
    except yaml.YAMLError as exc:
        raise ServiceError(f"base_config_yaml parse failed: {exc}", 422) from exc

    if parsed is None:
        parsed = {}

    if not isinstance(parsed, dict):
        raise ServiceError("base_config_yaml must be a YAML object", 422)


def _normalize_position(value: int | None, fallback: int) -> int:
    if value is None:
        return fallback
    return value


def _dedupe_keep_order(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        output.append(value)
        seen.add(value)
    return output


async def create_main_config(db: AsyncSession, payload: MainConfigCreate) -> MainConfig:
    await _assert_unique_config_name(db, payload.name)
    validate_base_yaml(payload.base_config_yaml)

    config = MainConfig(
        name=payload.name,
        password_plain=payload.password_plain,
        base_config_yaml=payload.base_config_yaml,
        enabled=payload.enabled,
        final_target_type=payload.final_target_type,
        final_target_group_name=payload.final_target_group_name,
    )

    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def update_main_config(db: AsyncSession, config: MainConfig, payload: MainConfigUpdate) -> MainConfig:
    if payload.name is not None and payload.name != config.name:
        await _assert_unique_config_name(db, payload.name, exclude_id=config.id)
        config.name = payload.name

    if payload.password_plain is not None:
        config.password_plain = payload.password_plain

    if payload.base_config_yaml is not None:
        validate_base_yaml(payload.base_config_yaml)
        config.base_config_yaml = payload.base_config_yaml

    if payload.enabled is not None:
        config.enabled = payload.enabled

    if payload.final_target_type is not None:
        config.final_target_type = payload.final_target_type

    if payload.final_target_group_name is not None:
        config.final_target_group_name = payload.final_target_group_name

    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def list_main_configs(db: AsyncSession) -> list[MainConfig]:
    result = await db.execute(select(MainConfig).order_by(MainConfig.created_at.desc()))
    return list(result.scalars().all())


async def get_main_config_or_404(db: AsyncSession, config_id: str) -> MainConfig:
    config = await db.get(MainConfig, config_id)
    if config is None:
        raise ServiceError("main config not found", 404)
    return config


async def delete_main_config(db: AsyncSession, config: MainConfig) -> None:
    await db.delete(config)
    await db.commit()


async def validate_builder_refs(db: AsyncSession, payload: BuilderPayload) -> None:
    subscription_ids = {
        rule.subscription_source_id
        for group in payload.filtered_groups
        for rule in group.rules
    }
    if subscription_ids:
        result = await db.execute(
            select(SubscriptionSource.id).where(SubscriptionSource.id.in_(subscription_ids))
        )
        found = set(result.scalars().all())
        missing = subscription_ids - found
        if missing:
            raise ServiceError(f"unknown subscription_source_id: {sorted(missing)}", 422)

    rule_ids = {item.rule_source_id for item in payload.shunt_bindings}
    if rule_ids:
        result = await db.execute(select(RuleSource.id).where(RuleSource.id.in_(rule_ids)))
        found = set(result.scalars().all())
        missing = rule_ids - found
        if missing:
            raise ServiceError(f"unknown rule_source_id: {sorted(missing)}", 422)


def validate_builder_shapes(payload: BuilderPayload) -> None:
    filtered_names = [item.name for item in payload.filtered_groups]
    manual_names = [item.name for item in payload.manual_groups]
    all_group_names = filtered_names + manual_names

    duplicates = {name for name in all_group_names if all_group_names.count(name) > 1}
    if duplicates:
        raise ServiceError(f"duplicated group names: {sorted(duplicates)}", 422)

    group_name_set = set(all_group_names)
    manual_set = set(manual_names)
    filtered_set = set(filtered_names)

    for group in payload.filtered_groups:
        for rule in group.rules:
            flags = 0
            if "i" in rule.regex_flags:
                flags |= re.IGNORECASE
            try:
                re.compile(rule.regex_pattern, flags)
            except re.error as exc:
                raise ServiceError(
                    f"invalid filtered regex {rule.regex_pattern}: {exc}",
                    422,
                ) from exc

    deps: dict[str, set[str]] = {}
    for group in payload.manual_groups:
        for member in group.members:
            if member.member_type == "filtered_group":
                if member.member_ref not in filtered_set:
                    raise ServiceError(
                        f"manual group {group.name} references unknown filtered group {member.member_ref}",
                        422,
                    )
            elif member.member_type == "manual_group":
                if member.member_ref not in manual_set:
                    raise ServiceError(
                        f"manual group {group.name} references unknown manual group {member.member_ref}",
                        422,
                    )
                deps.setdefault(group.name, set()).add(member.member_ref)
            else:
                raise ServiceError(
                    f"invalid member_type {member.member_type}",
                    422,
                )

    temp_mark: set[str] = set()
    perm_mark: set[str] = set()

    def visit(node: str) -> None:
        if node in perm_mark:
            return
        if node in temp_mark:
            raise ServiceError("manual group dependency cycle detected", 422)
        temp_mark.add(node)
        for dep in deps.get(node, set()):
            visit(dep)
        temp_mark.remove(node)
        perm_mark.add(node)

    for item in manual_set:
        visit(item)

    for item in payload.dialer_override_rules:
        if item.filtered_group_name not in filtered_set:
            raise ServiceError(
                f"dialer references unknown filtered group: {item.filtered_group_name}",
                422,
            )
        if item.dialer_group_name not in group_name_set:
            raise ServiceError(
                f"dialer group not found: {item.dialer_group_name}",
                422,
            )

    for binding in payload.shunt_bindings:
        if binding.default_group_name not in group_name_set | {"DIRECT", "REJECT"}:
            raise ServiceError(
                f"shunt default group not found: {binding.default_group_name}",
                422,
            )


async def get_builder(db: AsyncSession, config_id: str) -> BuilderPayload:
    config = await get_main_config_or_404(db, config_id)
    return BuilderPayload(
        filtered_groups=config.filtered_groups,
        manual_groups=config.manual_groups,
        dialer_override_rules=config.dialer_override_rules,
        shunt_bindings=config.shunt_bindings,
    )


async def replace_builder(db: AsyncSession, config_id: str, payload: BuilderPayload) -> BuilderPayload:
    await validate_builder_refs(db, payload)
    validate_builder_shapes(payload)

    config = await get_main_config_or_404(db, config_id)
    config.filtered_groups = payload.filtered_groups
    config.manual_groups = payload.manual_groups
    config.dialer_override_rules = payload.dialer_override_rules
    config.shunt_bindings = payload.shunt_bindings

    db.add(config)
    await db.commit()
    await db.refresh(config)

    return BuilderPayload(
        filtered_groups=config.filtered_groups,
        manual_groups=config.manual_groups,
        dialer_override_rules=config.dialer_override_rules,
        shunt_bindings=config.shunt_bindings,
    )


async def preview_filtered_group_matches(
    db: AsyncSession,
    payload: FilteredGroupPreviewRequest,
) -> FilteredGroupPreviewResponse:
    subscription_ids: list[str] = []
    seen_ids: set[str] = set()
    for group in payload.filtered_groups:
        for rule in group.rules:
            if rule.subscription_source_id and rule.subscription_source_id not in seen_ids:
                subscription_ids.append(rule.subscription_source_id)
                seen_ids.add(rule.subscription_source_id)

    subscription_map: dict[str, SubscriptionSource] = {}
    if subscription_ids:
        result = await db.execute(
            select(SubscriptionSource).where(SubscriptionSource.id.in_(subscription_ids))
        )
        subscription_map = {
            row.id: row
            for row in result.scalars().all()
        }

    ordered_sources: list[OrderedSource] = []
    for source_id in subscription_ids:
        source = subscription_map.get(source_id)
        if source is None or not source.enabled or not source.cached_proxies_json:
            continue
        ordered_sources.append(
            OrderedSource(
                source_id=source.id,
                source_name=source.name,
                cached_proxies=source.cached_proxies_json,
            )
        )

    pool_result = build_proxy_pool_with_collision_names(ordered_sources)
    proxies_by_source = pool_result.proxies_by_source

    preview_items: list[FilteredGroupPreviewItem] = []
    for group_index, group in enumerate(payload.filtered_groups):
        group_name = group.name or f"Filtered Group #{group_index + 1}"
        valid_rules: list[FilteredRuleMatch] = []
        issues: list[str] = []

        ordered_rules = sorted(
            list(enumerate(group.rules)),
            key=lambda item: _normalize_position(item[1].position, item[0] + 1),
        )
        for _, rule in ordered_rules:
            source_id = rule.subscription_source_id
            if not source_id:
                issues.append("Rule subscription is required.")
                continue

            source = subscription_map.get(source_id)
            if source is None:
                issues.append(f"Subscription not found: {source_id}")
                continue
            if not source.enabled:
                issues.append(f"Subscription disabled: {source.name}")
                continue
            if not source.cached_proxies_json:
                issues.append(f"Subscription has no cached proxies: {source.name}")
                continue

            regex_pattern = (rule.regex_pattern or "").strip()
            if not regex_pattern:
                issues.append("Regex pattern is required.")
                continue

            try:
                re.compile(
                    regex_pattern,
                    re.IGNORECASE if "i" in rule.regex_flags else 0,
                )
            except re.error as exc:
                issues.append(f"Invalid regex {regex_pattern}: {exc}")
                continue

            valid_rules.append(
                FilteredRuleMatch(
                    source_id=source_id,
                    regex_pattern=regex_pattern,
                    regex_flags=rule.regex_flags,
                )
            )

        matched_proxy_names = match_filtered_rules_on_proxies(
            valid_rules,
            proxies_by_source,
        )

        preview_items.append(
            FilteredGroupPreviewItem(
                name=group_name,
                matched_proxy_names=matched_proxy_names,
                issues=_dedupe_keep_order(issues),
            )
        )

    return FilteredGroupPreviewResponse(groups=preview_items)


async def set_final_target(
    db: AsyncSession,
    config: MainConfig,
    final_target_type: FinalTargetType,
    final_target_group_name: str | None,
) -> MainConfig:
    if final_target_type == "group" and not final_target_group_name:
        raise ServiceError("final_target_group_name required when final_target_type=group", 422)

    if final_target_type != "group":
        final_target_group_name = None

    config.final_target_type = final_target_type
    config.final_target_group_name = final_target_group_name

    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def validate_final_target_exists(db: AsyncSession, config: MainConfig) -> None:
    if config.final_target_type != "group":
        return

    assert config.final_target_group_name is not None
    names = {fg.name for fg in config.filtered_groups} | {mg.name for mg in config.manual_groups}
    if config.final_target_group_name not in names:
        raise ServiceError(
            f"final target group not found: {config.final_target_group_name}",
            422,
        )
