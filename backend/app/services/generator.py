from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from urllib.parse import quote_plus

from sqlalchemy import select
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
from app.services.common import GenerationError, slugify_name, utc_now


@dataclass
class GenerationDiagnosticsData:
    stale_subscription_ids: list[str]
    stale_rule_ids: list[str]
    warnings: list[str]


def _is_stale(next_refresh_at: datetime | None) -> bool:
    if next_refresh_at is None:
        return False
    return next_refresh_at <= utc_now()


def _build_group_obj(
    name: str,
    group_mode: str,
    proxies: list[str],
    test_url: str | None,
    test_interval_sec: int | None,
) -> dict:
    group: dict = {"name": name, "type": group_mode, "proxies": proxies}
    if group_mode in {"fallback", "url-test"}:
        group["url"] = test_url or settings.default_test_url
        group["interval"] = test_interval_sec or settings.default_test_interval
    return group


def _dedupe_keep_order(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        out.append(value)
        seen.add(value)
    return out


def build_proxy_pool_with_collision_names(
    ordered_sources: list[tuple[str, str, list[dict]]],
) -> tuple[list[dict], dict[str, list[dict]], dict[str, list[str]]]:
    proxy_pool: list[dict] = []
    proxies_by_source: dict[str, list[dict]] = {}

    for source_id, source_name, cached_proxies in ordered_sources:
        source_entries: list[dict] = []
        for idx, proxy in enumerate(cached_proxies):
            if not isinstance(proxy, dict):
                continue

            proxy_copy = dict(proxy)
            raw_name = proxy_copy.get("name")
            if not isinstance(raw_name, str) or not raw_name.strip():
                raw_name = f"proxy-{idx + 1}"

            proxy_copy["__raw_name"] = raw_name
            proxy_copy["__source_id"] = source_id
            proxy_copy["__source_name"] = source_name
            source_entries.append(proxy_copy)
            proxy_pool.append(proxy_copy)

        proxies_by_source[source_id] = source_entries

    used_names: set[str] = set()
    raw_to_final: dict[str, list[str]] = {}

    for proxy in proxy_pool:
        raw_name = str(proxy.get("__raw_name", "proxy"))
        source_slug = slugify_name(str(proxy.get("__source_name", "source")))

        candidate = raw_name
        if candidate in used_names:
            candidate = f"{raw_name}@{source_slug}"

        if candidate in used_names:
            suffix = 2
            while f"{candidate}#{suffix}" in used_names:
                suffix += 1
            candidate = f"{candidate}#{suffix}"

        proxy["name"] = candidate
        used_names.add(candidate)
        raw_to_final.setdefault(raw_name, []).append(candidate)

    return proxy_pool, proxies_by_source, raw_to_final


def match_filtered_rules_on_proxies(
    rules: list[tuple[str, str, str]],
    proxies_by_source: dict[str, list[dict]],
) -> list[str]:
    matched_names: list[str] = []
    for source_id, regex_pattern, regex_flags in rules:
        flags = re.IGNORECASE if "i" in regex_flags else 0
        pattern = re.compile(regex_pattern, flags)
        for proxy in proxies_by_source.get(source_id, []):
            name = str(proxy.get("name", ""))
            raw_name = str(proxy.get("__raw_name", ""))
            if pattern.search(name) or pattern.search(raw_name):
                matched_names.append(name)

    return _dedupe_keep_order(matched_names)


async def _load_builder_state(db: AsyncSession, config_id: str) -> dict:
    fg_result = await db.execute(
        select(FilteredGroup)
        .where(FilteredGroup.main_config_id == config_id)
        .order_by(FilteredGroup.position.asc())
    )
    filtered_groups = list(fg_result.scalars().all())
    fg_ids = [item.id for item in filtered_groups]

    fg_rules: list[FilteredGroupRule] = []
    if fg_ids:
        fg_rule_result = await db.execute(
            select(FilteredGroupRule)
            .where(FilteredGroupRule.filtered_group_id.in_(fg_ids))
            .order_by(FilteredGroupRule.position.asc())
        )
        fg_rules = list(fg_rule_result.scalars().all())

    sub_ids_ordered: list[str] = []
    seen_sub_ids: set[str] = set()
    fg_id_order = {fg.id: idx for idx, fg in enumerate(filtered_groups)}
    for rule in sorted(fg_rules, key=lambda r: (fg_id_order.get(r.filtered_group_id, 0), r.position)):
        if rule.subscription_source_id not in seen_sub_ids:
            sub_ids_ordered.append(rule.subscription_source_id)
            seen_sub_ids.add(rule.subscription_source_id)

    subscriptions: list[SubscriptionSource] = []
    if sub_ids_ordered:
        sub_result = await db.execute(
            select(SubscriptionSource).where(SubscriptionSource.id.in_(sub_ids_ordered))
        )
        subscriptions = list(sub_result.scalars().all())
    sub_map = {item.id: item for item in subscriptions}

    mg_result = await db.execute(
        select(ManualGroup)
        .where(ManualGroup.main_config_id == config_id)
        .order_by(ManualGroup.position.asc())
    )
    manual_groups = list(mg_result.scalars().all())
    mg_ids = [item.id for item in manual_groups]

    mg_members: list[ManualGroupMember] = []
    if mg_ids:
        mg_member_result = await db.execute(
            select(ManualGroupMember)
            .where(ManualGroupMember.manual_group_id.in_(mg_ids))
            .order_by(ManualGroupMember.position.asc())
        )
        mg_members = list(mg_member_result.scalars().all())

    dialer_result = await db.execute(
        select(DialerOverrideRule)
        .where(DialerOverrideRule.main_config_id == config_id)
        .order_by(DialerOverrideRule.position.asc())
    )
    dialer_rules = list(dialer_result.scalars().all())

    shunt_result = await db.execute(
        select(ShuntBinding)
        .where(ShuntBinding.main_config_id == config_id)
        .order_by(ShuntBinding.position.asc())
    )
    shunt_bindings = list(shunt_result.scalars().all())
    rule_ids = [item.rule_source_id for item in shunt_bindings]

    rules: list[RuleSource] = []
    if rule_ids:
        rules_result = await db.execute(select(RuleSource).where(RuleSource.id.in_(rule_ids)))
        rules = list(rules_result.scalars().all())
    rule_map = {item.id: item for item in rules}

    return {
        "sub_ids_ordered": sub_ids_ordered,
        "sub_map": sub_map,
        "filtered_groups": filtered_groups,
        "filtered_rules": fg_rules,
        "manual_groups": manual_groups,
        "manual_members": mg_members,
        "dialer_rules": dialer_rules,
        "shunt_bindings": shunt_bindings,
        "rule_map": rule_map,
    }


async def generate_config_yaml(
    db: AsyncSession,
    config: MainConfig,
    enqueue_subscription_refresh,
    enqueue_rule_refresh,
) -> tuple[str, GenerationDiagnosticsData]:
    state = await _load_builder_state(db, config.id)

    diagnostics = GenerationDiagnosticsData(
        stale_subscription_ids=[],
        stale_rule_ids=[],
        warnings=[],
    )

    sub_ids_ordered: list[str] = state["sub_ids_ordered"]
    sub_map: dict[str, SubscriptionSource] = state["sub_map"]

    ordered_sources: list[tuple[str, str, list[dict]]] = []

    for source_id in sub_ids_ordered:
        source = sub_map.get(source_id)
        if source is None:
            diagnostics.warnings.append(f"subscription not found: {source_id}")
            continue
        if not source.enabled:
            diagnostics.warnings.append(f"subscription disabled: {source.name}")
            continue

        if source.mode == "remote" and source.auto_update and _is_stale(source.next_refresh_at):
            diagnostics.stale_subscription_ids.append(source.id)
            await enqueue_subscription_refresh(source.id)

        if not source.cached_proxies_json:
            raise GenerationError(
                f"subscription has no cached proxies: {source.name}",
                409,
            )

        ordered_sources.append(
            (source.id, source.name, source.cached_proxies_json),
        )

    proxy_pool, proxies_by_source, _ = build_proxy_pool_with_collision_names(
        ordered_sources
    )

    filtered_groups = state["filtered_groups"]
    filtered_rules = state["filtered_rules"]
    fg_rules_map: dict[str, list[FilteredGroupRule]] = {}
    for row in filtered_rules:
        fg_rules_map.setdefault(row.filtered_group_id, []).append(row)

    generated_filtered_groups: list[dict] = []
    filtered_group_members: dict[str, list[str]] = {}

    for group in filtered_groups:
        members = match_filtered_rules_on_proxies(
            [
                (
                    rule.subscription_source_id,
                    rule.regex_pattern,
                    rule.regex_flags,
                )
                for rule in fg_rules_map.get(group.id, [])
            ],
            proxies_by_source,
        )
        if not members:
            raise GenerationError(f"filtered group has no matched proxies: {group.name}", 422)

        filtered_group_members[group.name] = members
        generated_filtered_groups.append(
            _build_group_obj(
                group.name,
                group.group_mode,
                members,
                group.test_url,
                group.test_interval_sec,
            )
        )

    manual_groups = state["manual_groups"]
    manual_members = state["manual_members"]

    mg_row_by_name = {row.name: row for row in manual_groups}
    mg_members_map: dict[str, list[ManualGroupMember]] = {}
    for member in manual_members:
        mg_members_map.setdefault(member.manual_group_id, []).append(member)

    manual_resolved: dict[str, list[str]] = {}
    resolving: set[str] = set()

    def resolve_manual_group(name: str) -> list[str]:
        if name in manual_resolved:
            return manual_resolved[name]
        if name in resolving:
            raise GenerationError("manual group dependency cycle detected", 422)

        row = mg_row_by_name.get(name)
        if row is None:
            raise GenerationError(f"manual group not found: {name}", 422)

        resolving.add(name)
        members: list[str] = []
        for member in mg_members_map.get(row.id, []):
            if member.member_type == "filtered_group":
                if member.member_ref not in filtered_group_members:
                    raise GenerationError(
                        f"manual group {name} references unknown filtered group {member.member_ref}",
                        422,
                    )
                members.append(member.member_ref)
            elif member.member_type == "manual_group":
                _ = resolve_manual_group(member.member_ref)
                members.append(member.member_ref)
            else:
                raise GenerationError(
                    f"invalid manual group member type: {member.member_type}",
                    422,
                )

        members = _dedupe_keep_order(members)
        if not members:
            raise GenerationError(f"manual group has no members: {name}", 422)

        manual_resolved[name] = members
        resolving.remove(name)
        return members

    generated_manual_groups: list[dict] = []
    for row in manual_groups:
        members = resolve_manual_group(row.name)
        generated_manual_groups.append(
            _build_group_obj(
                row.name,
                row.group_mode,
                members,
                row.test_url,
                row.test_interval_sec,
            )
        )

    group_names_filtered = [row.name for row in filtered_groups]
    group_names_manual = [row.name for row in manual_groups]
    available_non_shunt_groups = set(group_names_filtered + group_names_manual)

    proxy_by_name = {str(p.get("name", "")): p for p in proxy_pool}
    matched_dialer_proxy_names: set[str] = set()
    for rule in state["dialer_rules"]:
        if rule.dialer_group_name not in available_non_shunt_groups:
            raise GenerationError(
                f"dialer group not found: {rule.dialer_group_name}",
                422,
            )
        if rule.filtered_group_name not in filtered_group_members:
            raise GenerationError(
                f"dialer references unknown filtered group: {rule.filtered_group_name}",
                422,
            )
        for proxy_name in filtered_group_members[rule.filtered_group_name]:
            if proxy_name not in matched_dialer_proxy_names:
                proxy = proxy_by_name.get(proxy_name)
                if proxy is not None:
                    proxy["dialer-proxy"] = rule.dialer_group_name
                    matched_dialer_proxy_names.add(proxy_name)

    shunt_bindings = state["shunt_bindings"]
    rule_map: dict[str, RuleSource] = state["rule_map"]

    generated_shunt_groups: list[dict] = []
    rule_providers: dict[str, dict] = {}
    rules: list[str] = []

    provider_keys_used: set[str] = set()

    manual_ordered_names = [row.name for row in manual_groups]
    filtered_ordered_names = [row.name for row in filtered_groups]

    for idx, binding in enumerate(shunt_bindings, start=1):
        if binding.default_group_name not in available_non_shunt_groups | {"DIRECT", "REJECT"}:
            raise GenerationError(
                f"shunt default group not found: {binding.default_group_name}",
                422,
            )

        rule_source = rule_map.get(binding.rule_source_id)
        if rule_source is None:
            raise GenerationError(
                f"rule source not found for binding {binding.binding_name}",
                422,
            )
        if not rule_source.enabled:
            raise GenerationError(
                f"rule source disabled for binding {binding.binding_name}",
                422,
            )
        if not rule_source.cached_payload_lines_json:
            raise GenerationError(
                f"rule source has no cache: {rule_source.name}",
                409,
            )

        if rule_source.mode == "remote" and rule_source.auto_update and _is_stale(rule_source.next_refresh_at):
            diagnostics.stale_rule_ids.append(rule_source.id)
            await enqueue_rule_refresh(rule_source.id)

        shunt_group_members = _dedupe_keep_order(
            [binding.default_group_name, "DIRECT"]
            + manual_ordered_names
            + filtered_ordered_names
            + ["REJECT"]
        )
        generated_shunt_groups.append(
            {
                "name": binding.binding_name,
                "type": "select",
                "proxies": shunt_group_members,
            }
        )

        key_base = slugify_name(binding.binding_name).replace("-", "_")
        provider_key = key_base or f"rule_provider_{idx}"
        if provider_key in provider_keys_used:
            suffix = 2
            while f"{provider_key}_{suffix}" in provider_keys_used:
                suffix += 1
            provider_key = f"{provider_key}_{suffix}"
        provider_keys_used.add(provider_key)

        password = quote_plus(config.password_plain)
        rule_url = (
            f"{settings.public_base_url.rstrip('/')}{settings.api_prefix}/public/"
            f"configs/{config.id}/rules/{rule_source.id}.yaml?{settings.query_password_name}={password}"
        )

        rule_providers[provider_key] = {
            "type": "http",
            "behavior": rule_source.behavior,
            "format": "yaml",
            "path": f"./rules/{rule_source.id}.yaml",
            "url": rule_url,
            "interval": rule_source.update_interval_sec,
        }

        line = f"RULE-SET,{provider_key},{binding.binding_name}"
        if binding.no_resolve:
            line += ",no-resolve"
        rules.append(line)

    final_target: str
    if config.final_target_type == "group":
        if not config.final_target_group_name:
            raise GenerationError("final target group is required", 422)
        if config.final_target_group_name not in available_non_shunt_groups:
            raise GenerationError(
                f"final target group not found: {config.final_target_group_name}",
                422,
            )
        final_target = config.final_target_group_name
    elif config.final_target_type in {"DIRECT", "REJECT"}:
        final_target = config.final_target_type
    else:
        raise GenerationError("invalid final target type", 422)

    rules.append(f"MATCH,{final_target}")

    generated_proxy_groups = (
        generated_filtered_groups + generated_manual_groups + generated_shunt_groups
    )

    all_group_names = {group["name"] for group in generated_proxy_groups}
    referenced_proxy_names: set[str] = set()
    for group in generated_proxy_groups:
        for member in group.get("proxies", []):
            if member in {"DIRECT", "REJECT"}:
                continue
            if member in all_group_names:
                continue
            referenced_proxy_names.add(member)

    final_proxies: list[dict] = []
    for proxy in proxy_pool:
        proxy_name = str(proxy.get("name", ""))
        if proxy_name in referenced_proxy_names:
            out = {k: v for k, v in proxy.items() if not k.startswith("__")}
            final_proxies.append(out)

    try:
        base = yaml.safe_load(config.base_config_yaml)
    except yaml.YAMLError as exc:
        raise GenerationError(f"base config yaml parse failed: {exc}", 422) from exc

    if base is None:
        base = {}
    if not isinstance(base, dict):
        raise GenerationError("base config YAML must be object", 422)

    base["proxies"] = final_proxies
    base["proxy-groups"] = generated_proxy_groups
    base["rule-providers"] = rule_providers
    base["rules"] = rules

    rendered = yaml.safe_dump(base, allow_unicode=True, sort_keys=False)
    return rendered, diagnostics


async def render_rule_source_yaml(rule_source: RuleSource) -> str:
    if not rule_source.cached_payload_lines_json:
        raise GenerationError(f"rule source has no cached payload: {rule_source.name}", 409)

    content = {"payload": rule_source.cached_payload_lines_json}
    return yaml.safe_dump(content, allow_unicode=True, sort_keys=False)
