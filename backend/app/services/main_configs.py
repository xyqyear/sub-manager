from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import yaml

from app.models import (
    MainConfig,
    RouteTemplate,
    RuleSource,
    SubscriptionSource,
)
from app.schemas.configs import (
    FilteredGroupPayload,
    FilteredGroupPreviewItem,
    FilteredGroupPreviewRequest,
    FilteredGroupPreviewResponse,
    FilteredGroupPreviewRuleResult,
    MainConfigCreate,
    MainConfigUpdate,
    ManualGroupPayload,
    DialerOverridePayload,
    SlotMappingPayload,
)
from app.services.common import ServiceError
from app.services.generator import (
    OrderedSource,
    build_proxy_pool_with_collision_names,
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



async def create_main_config(db: AsyncSession, payload: MainConfigCreate) -> MainConfig:
    await _assert_unique_config_name(db, payload.name)
    validate_base_yaml(payload.base_config_yaml)

    if payload.filtered_groups or payload.manual_groups or payload.dialer_override_rules:
        validate_builder_shapes(
            payload.filtered_groups, payload.manual_groups,
            payload.dialer_override_rules,
        )
        await validate_builder_refs(db, payload.filtered_groups)

    group_name_set = _collect_group_names(payload.filtered_groups, payload.manual_groups)
    await validate_slot_mappings(db, payload.route_template_id, payload.slot_mappings, group_name_set)

    config = MainConfig(
        name=payload.name,
        base_config_yaml=payload.base_config_yaml,
        enabled=payload.enabled,
        final_target_type=payload.final_target_type,
        final_target_group_name=payload.final_target_group_name,
        filtered_groups=payload.filtered_groups,
        manual_groups=payload.manual_groups,
        dialer_override_rules=payload.dialer_override_rules,
        route_template_id=payload.route_template_id,
        slot_mappings=payload.slot_mappings,
    )

    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def update_main_config(db: AsyncSession, config: MainConfig, payload: MainConfigUpdate) -> MainConfig:
    if payload.name is not None and payload.name != config.name:
        await _assert_unique_config_name(db, payload.name, exclude_id=config.id)
        config.name = payload.name

    if payload.base_config_yaml is not None:
        validate_base_yaml(payload.base_config_yaml)
        config.base_config_yaml = payload.base_config_yaml

    if payload.enabled is not None:
        config.enabled = payload.enabled

    if payload.final_target_type is not None:
        config.final_target_type = payload.final_target_type

    if payload.final_target_group_name is not None:
        config.final_target_group_name = payload.final_target_group_name

    builder_changed = any(
        getattr(payload, f) is not None
        for f in ("filtered_groups", "manual_groups", "dialer_override_rules")
    )
    if builder_changed:
        fg = payload.filtered_groups if payload.filtered_groups is not None else config.filtered_groups
        mg = payload.manual_groups if payload.manual_groups is not None else config.manual_groups
        dor = payload.dialer_override_rules if payload.dialer_override_rules is not None else config.dialer_override_rules
        validate_builder_shapes(fg, mg, dor)
        await validate_builder_refs(db, fg)
        config.filtered_groups = fg
        config.manual_groups = mg
        config.dialer_override_rules = dor

    route_changed = payload.route_template_id is not None or payload.slot_mappings is not None
    if route_changed or builder_changed:
        fg = config.filtered_groups
        mg = config.manual_groups
        rt_id = payload.route_template_id if payload.route_template_id is not None else config.route_template_id
        sm = payload.slot_mappings if payload.slot_mappings is not None else config.slot_mappings
        group_name_set = _collect_group_names(fg, mg)
        await validate_slot_mappings(db, rt_id, sm, group_name_set)
        config.route_template_id = rt_id
        config.slot_mappings = sm

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


async def validate_builder_refs(
    db: AsyncSession,
    filtered_groups: list[FilteredGroupPayload],
) -> None:
    subscription_ids = {
        rule.subscription_source_id
        for group in filtered_groups
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


def validate_builder_shapes(
    filtered_groups: list[FilteredGroupPayload],
    manual_groups: list[ManualGroupPayload],
    dialer_override_rules: list[DialerOverridePayload],
) -> None:
    filtered_names = [item.name for item in filtered_groups]
    manual_names = [item.name for item in manual_groups]
    all_group_names = filtered_names + manual_names

    duplicates = {name for name in all_group_names if all_group_names.count(name) > 1}
    if duplicates:
        raise ServiceError(f"duplicated group names: {sorted(duplicates)}", 422)

    group_name_set = set(all_group_names)
    manual_set = set(manual_names)
    filtered_set = set(filtered_names)

    for group in filtered_groups:
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
    for group in manual_groups:
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

    for item in dialer_override_rules:
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


def _collect_group_names(
    filtered_groups: list[FilteredGroupPayload],
    manual_groups: list[ManualGroupPayload],
) -> set[str]:
    return {g.name for g in filtered_groups} | {g.name for g in manual_groups}


async def validate_slot_mappings(
    db: AsyncSession,
    route_template_id: str | None,
    slot_mappings: list[SlotMappingPayload],
    group_name_set: set[str],
) -> None:
    if not route_template_id:
        return

    template = await db.get(RouteTemplate, route_template_id)
    if template is None:
        raise ServiceError(f"route template not found: {route_template_id}", 422)

    slot_names = {s.name for s in template.slots}
    mapped_slots = {m.slot_name for m in slot_mappings}
    missing = slot_names - mapped_slots
    if missing:
        raise ServiceError(f"unmapped slots: {sorted(missing)}", 422)

    for mapping in slot_mappings:
        if mapping.slot_name not in slot_names:
            raise ServiceError(f"slot mapping references unknown slot: {mapping.slot_name}", 422)
        if mapping.group_name not in group_name_set | {"DIRECT", "REJECT"}:
            raise ServiceError(f"slot mapping group not found: {mapping.group_name}", 422)


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
        rule_results: list[FilteredGroupPreviewRuleResult] = []

        for rule in group.rules:
            source_id = rule.subscription_source_id
            if not source_id:
                rule_results.append(FilteredGroupPreviewRuleResult(matched_proxy_names=[], issue="Rule subscription is required."))
                continue

            source = subscription_map.get(source_id)
            if source is None:
                rule_results.append(FilteredGroupPreviewRuleResult(matched_proxy_names=[], issue=f"Subscription not found: {source_id}"))
                continue
            if not source.enabled:
                rule_results.append(FilteredGroupPreviewRuleResult(matched_proxy_names=[], issue=f"Subscription disabled: {source.name}"))
                continue
            if not source.cached_proxies_json:
                rule_results.append(FilteredGroupPreviewRuleResult(matched_proxy_names=[], issue=f"Subscription has no cached proxies: {source.name}"))
                continue

            regex_pattern = (rule.regex_pattern or "").strip()
            if not regex_pattern:
                rule_results.append(FilteredGroupPreviewRuleResult(matched_proxy_names=[], issue="Regex pattern is required."))
                continue

            try:
                compiled = re.compile(
                    regex_pattern,
                    re.IGNORECASE if "i" in rule.regex_flags else 0,
                )
            except re.error as exc:
                rule_results.append(FilteredGroupPreviewRuleResult(matched_proxy_names=[], issue=f"Invalid regex {regex_pattern}: {exc}"))
                continue

            matched: list[str] = []
            source_proxies = proxies_by_source.get(source_id, [])
            for proxy in source_proxies:
                final_name = proxy.get("name", "")
                raw_name = proxy.get("__raw_name", final_name)
                if compiled.search(final_name) or compiled.search(raw_name):
                    matched.append(final_name)

            rule_results.append(FilteredGroupPreviewRuleResult(matched_proxy_names=matched))

        preview_items.append(
            FilteredGroupPreviewItem(
                name=group_name,
                rule_results=rule_results,
            )
        )

    return FilteredGroupPreviewResponse(groups=preview_items)
