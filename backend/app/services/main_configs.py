from __future__ import annotations

from collections import defaultdict
import re

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
import yaml

from app.config import settings
from app.models import (
    DialerOverrideRule,
    FilteredGroup,
    FilteredGroupRule,
    MainConfig,
    ManualGroup,
    ManualGroupMember,
    RuleSource,
    ShuntBinding,
    SubscriptionSource,
)
from app.schemas.configs import (
    BuilderPayload,
    BuilderRead,
    DialerOverridePayload,
    FilteredGroupPreviewItem,
    FilteredGroupPreviewRequest,
    FilteredGroupPreviewResponse,
    FilteredGroupPayload,
    FilteredGroupRulePayload,
    MainConfigCreate,
    MainConfigRead,
    MainConfigUpdate,
    ManualGroupMemberPayload,
    ManualGroupPayload,
    ShuntBindingPayload,
)
from app.services.common import ServiceError
from app.services.generator import (
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


def _validate_base_yaml(base_config_yaml: str) -> None:
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
    _validate_base_yaml(payload.base_config_yaml)

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
        _validate_base_yaml(payload.base_config_yaml)
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


async def _validate_builder_refs(db: AsyncSession, payload: BuilderPayload) -> None:
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


def _validate_builder_shapes(payload: BuilderPayload) -> None:
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

    deps: dict[str, set[str]] = defaultdict(set)
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
                deps[group.name].add(member.member_ref)
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


async def get_builder(db: AsyncSession, config_id: str) -> BuilderRead:
    fg_result = await db.execute(
        select(FilteredGroup).where(FilteredGroup.main_config_id == config_id).order_by(FilteredGroup.position.asc())
    )
    fg_rows = list(fg_result.scalars().all())
    fg_ids = [item.id for item in fg_rows]

    fg_rules_map: dict[str, list[FilteredGroupRulePayload]] = defaultdict(list)
    if fg_ids:
        fg_rule_result = await db.execute(
            select(FilteredGroupRule).where(FilteredGroupRule.filtered_group_id.in_(fg_ids)).order_by(FilteredGroupRule.position.asc())
        )
        for rule in fg_rule_result.scalars().all():
            fg_rules_map[rule.filtered_group_id].append(
                FilteredGroupRulePayload(
                    subscription_source_id=rule.subscription_source_id,
                    regex_pattern=rule.regex_pattern,
                    regex_flags=rule.regex_flags,
                    position=rule.position,
                )
            )

    filtered_groups = [
        FilteredGroupPayload(
            name=item.name,
            position=item.position,
            group_mode=item.group_mode,
            test_url=item.test_url,
            test_interval_sec=item.test_interval_sec,
            rules=fg_rules_map.get(item.id, []),
        )
        for item in fg_rows
    ]

    mg_result = await db.execute(
        select(ManualGroup).where(ManualGroup.main_config_id == config_id).order_by(ManualGroup.position.asc())
    )
    mg_rows = list(mg_result.scalars().all())
    mg_ids = [item.id for item in mg_rows]

    mg_members_map: dict[str, list[ManualGroupMemberPayload]] = defaultdict(list)
    if mg_ids:
        mg_member_result = await db.execute(
            select(ManualGroupMember).where(ManualGroupMember.manual_group_id.in_(mg_ids)).order_by(ManualGroupMember.position.asc())
        )
        for member in mg_member_result.scalars().all():
            mg_members_map[member.manual_group_id].append(
                ManualGroupMemberPayload(
                    member_type=member.member_type,
                    member_ref=member.member_ref,
                    position=member.position,
                )
            )

    manual_groups = [
        ManualGroupPayload(
            name=item.name,
            position=item.position,
            group_mode=item.group_mode,
            test_url=item.test_url,
            test_interval_sec=item.test_interval_sec,
            members=mg_members_map.get(item.id, []),
        )
        for item in mg_rows
    ]

    dor_result = await db.execute(
        select(DialerOverrideRule).where(DialerOverrideRule.main_config_id == config_id).order_by(DialerOverrideRule.position.asc())
    )
    dialer_override_rules = [
        DialerOverridePayload(
            filtered_group_name=item.filtered_group_name,
            dialer_group_name=item.dialer_group_name,
        )
        for item in dor_result.scalars().all()
    ]

    shunt_result = await db.execute(
        select(ShuntBinding).where(ShuntBinding.main_config_id == config_id).order_by(ShuntBinding.position.asc())
    )
    shunt_bindings = [
        ShuntBindingPayload(
            position=item.position,
            binding_name=item.binding_name,
            rule_source_id=item.rule_source_id,
            default_group_name=item.default_group_name,
            no_resolve=item.no_resolve,
        )
        for item in shunt_result.scalars().all()
    ]

    return BuilderRead(
        filtered_groups=filtered_groups,
        manual_groups=manual_groups,
        dialer_override_rules=dialer_override_rules,
        shunt_bindings=shunt_bindings,
    )


async def replace_builder(db: AsyncSession, config_id: str, payload: BuilderPayload) -> BuilderRead:
    await _validate_builder_refs(db, payload)
    _validate_builder_shapes(payload)

    fg_result = await db.execute(
        select(FilteredGroup).where(FilteredGroup.main_config_id == config_id)
    )
    old_fg_ids = [item.id for item in fg_result.scalars().all()]
    if old_fg_ids:
        await db.execute(delete(FilteredGroupRule).where(FilteredGroupRule.filtered_group_id.in_(old_fg_ids)))
    await db.execute(delete(FilteredGroup).where(FilteredGroup.main_config_id == config_id))

    mg_result = await db.execute(
        select(ManualGroup).where(ManualGroup.main_config_id == config_id)
    )
    old_mg_ids = [item.id for item in mg_result.scalars().all()]
    if old_mg_ids:
        await db.execute(delete(ManualGroupMember).where(ManualGroupMember.manual_group_id.in_(old_mg_ids)))
    await db.execute(delete(ManualGroup).where(ManualGroup.main_config_id == config_id))

    await db.execute(
        delete(DialerOverrideRule).where(DialerOverrideRule.main_config_id == config_id)
    )
    await db.execute(delete(ShuntBinding).where(ShuntBinding.main_config_id == config_id))

    fg_name_to_id: dict[str, str] = {}
    for group in payload.filtered_groups:
        row = FilteredGroup(
            main_config_id=config_id,
            name=group.name,
            position=group.position,
            group_mode=group.group_mode,
            test_url=group.test_url or settings.default_test_url,
            test_interval_sec=group.test_interval_sec or settings.default_test_interval,
        )
        db.add(row)
        await db.flush()
        fg_name_to_id[group.name] = row.id

        for rule in group.rules:
            db.add(
                FilteredGroupRule(
                    filtered_group_id=row.id,
                    subscription_source_id=rule.subscription_source_id,
                    regex_pattern=rule.regex_pattern,
                    regex_flags=rule.regex_flags,
                    position=rule.position,
                )
            )

    mg_name_to_id: dict[str, str] = {}
    for group in payload.manual_groups:
        row = ManualGroup(
            main_config_id=config_id,
            name=group.name,
            position=group.position,
            group_mode=group.group_mode,
            test_url=group.test_url or settings.default_test_url,
            test_interval_sec=group.test_interval_sec or settings.default_test_interval,
        )
        db.add(row)
        await db.flush()
        mg_name_to_id[group.name] = row.id

        for member in group.members:
            db.add(
                ManualGroupMember(
                    manual_group_id=row.id,
                    member_type=member.member_type,
                    member_ref=member.member_ref,
                    position=member.position,
                )
            )

    for index, rule in enumerate(payload.dialer_override_rules, start=1):
        db.add(
            DialerOverrideRule(
                main_config_id=config_id,
                filtered_group_name=rule.filtered_group_name,
                dialer_group_name=rule.dialer_group_name,
                position=index,
            )
        )

    for binding in payload.shunt_bindings:
        db.add(
            ShuntBinding(
                main_config_id=config_id,
                position=binding.position,
                binding_name=binding.binding_name,
                rule_source_id=binding.rule_source_id,
                default_group_name=binding.default_group_name,
                no_resolve=binding.no_resolve,
            )
        )

    await db.commit()
    return await get_builder(db, config_id)


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

    ordered_sources: list[tuple[str, str, list[dict]]] = []
    for source_id in subscription_ids:
        source = subscription_map.get(source_id)
        if source is None or not source.enabled or not source.cached_proxies_json:
            continue
        ordered_sources.append((source.id, source.name, source.cached_proxies_json))

    _, proxies_by_source, _ = build_proxy_pool_with_collision_names(ordered_sources)

    preview_items: list[FilteredGroupPreviewItem] = []
    for group_index, group in enumerate(payload.filtered_groups):
        group_name = group.name or f"Filtered Group #{group_index + 1}"
        valid_rules: list[tuple[str, str, str]] = []
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

            valid_rules.append((source_id, regex_pattern, rule.regex_flags))

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
    final_target_type: str,
    final_target_group_name: str | None,
) -> MainConfig:
    if final_target_type not in {"DIRECT", "REJECT", "group"}:
        raise ServiceError("final_target_type must be DIRECT, REJECT, or group", 422)

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
    result = await db.execute(
        select(FilteredGroup.name)
        .where(FilteredGroup.main_config_id == config.id)
        .union(
            select(ManualGroup.name).where(ManualGroup.main_config_id == config.id)
        )
    )
    names = set(result.scalars().all())
    if config.final_target_group_name not in names:
        raise ServiceError(
            f"final target group not found: {config.final_target_group_name}",
            422,
        )
