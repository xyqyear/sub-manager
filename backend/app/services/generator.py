from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any
from pydantic import BaseModel, ConfigDict
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
    DialerOverridePayload,
    DraftPreviewRequest,
    FilteredGroupPayload,
    ManualGroupPayload,
    RouteBindingPayload,
)
from app.services.common import GenerationError, dedupe_keep_order, slugify_name, utc_now
from app.services.refresh_loop import refresh_loop_manager


class GenerationDiagnosticsData(BaseModel):
    stale_subscription_ids: list[str]
    stale_rule_ids: list[str]
    warnings: list[str]


class GenerationInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    config_id: str | None = None
    base_config_yaml: str
    final_target_type: str
    final_target_group_name: str | None = None
    public_base_url: str = ""
    filtered_groups: list[FilteredGroupPayload] = []
    manual_groups: list[ManualGroupPayload] = []
    dialer_override_rules: list[DialerOverridePayload] = []
    route_bindings: list[RouteBindingPayload] = []

    @staticmethod
    def from_main_config(config: MainConfig, *, public_base_url: str) -> GenerationInput:
        return GenerationInput(
            config_id=config.id,
            base_config_yaml=config.base_config_yaml,
            final_target_type=config.final_target_type,
            final_target_group_name=config.final_target_group_name,
            public_base_url=public_base_url,
            filtered_groups=config.filtered_groups,
            manual_groups=config.manual_groups,
            dialer_override_rules=config.dialer_override_rules,
            route_bindings=config.route_bindings,
        )

    @staticmethod
    def from_draft(draft: DraftPreviewRequest, *, public_base_url: str) -> GenerationInput:
        return GenerationInput(
            config_id=draft.config_id,
            base_config_yaml=draft.base_config_yaml,
            final_target_type=draft.final_target_type,
            final_target_group_name=draft.final_target_group_name,
            public_base_url=public_base_url,
            filtered_groups=draft.filtered_groups,
            manual_groups=draft.manual_groups,
            dialer_override_rules=draft.dialer_override_rules,
            route_bindings=draft.route_bindings,
        )


class OrderedSource(BaseModel):
    source_id: str
    source_name: str
    cached_proxies: list[dict[str, Any]]


class FilteredRuleMatch(BaseModel):
    source_id: str
    regex_pattern: str
    regex_flags: str


class ProxyPoolResult(BaseModel):
    proxy_pool: list[dict[str, Any]]
    proxies_by_source: dict[str, list[dict[str, Any]]]
    raw_to_final: dict[str, list[str]]


class GenerationResult(BaseModel):
    yaml: str
    diagnostics: GenerationDiagnosticsData


class ProxyGroupObj(BaseModel):
    name: str
    type: str
    proxies: list[str]
    url: str | None = None
    interval: int | None = None


class RuleProviderObj(BaseModel):
    type: str
    behavior: str
    format: str
    path: str
    url: str
    interval: int


@dataclass
class GenerationContext:
    source: GenerationInput
    diagnostics: GenerationDiagnosticsData
    pool_result: ProxyPoolResult | None = None
    filtered_groups: list[ProxyGroupObj] = field(default_factory=list)
    filtered_group_members: dict[str, list[str]] = field(default_factory=dict)
    manual_groups: list[ProxyGroupObj] = field(default_factory=list)
    group_names_filtered: list[str] = field(default_factory=list)
    group_names_manual: list[str] = field(default_factory=list)
    available_non_route_groups: set[str] = field(default_factory=set)
    route_groups: list[ProxyGroupObj] = field(default_factory=list)
    rule_providers: dict[str, RuleProviderObj] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
) -> ProxyGroupObj:
    group = ProxyGroupObj(name=name, type=group_mode, proxies=proxies)
    if group_mode in {"fallback", "url-test"}:
        group.url = test_url or settings.default_test_url
        group.interval = test_interval_sec or settings.default_test_interval
    return group


# ---------------------------------------------------------------------------
# Step 3 (unchanged): build_proxy_pool_with_collision_names
# ---------------------------------------------------------------------------

def build_proxy_pool_with_collision_names(
    ordered_sources: list[OrderedSource],
) -> ProxyPoolResult:
    proxy_pool: list[dict[str, Any]] = []
    proxies_by_source: dict[str, list[dict[str, Any]]] = {}

    for source in ordered_sources:
        source_entries: list[dict[str, Any]] = []
        for idx, proxy in enumerate(source.cached_proxies):
            if not isinstance(proxy, dict):
                continue

            proxy_copy = dict(proxy)
            raw_name = proxy_copy.get("name")
            if not isinstance(raw_name, str) or not raw_name.strip():
                raw_name = f"proxy-{idx + 1}"

            proxy_copy["__raw_name"] = raw_name
            proxy_copy["__source_id"] = source.source_id
            proxy_copy["__source_name"] = source.source_name
            source_entries.append(proxy_copy)
            proxy_pool.append(proxy_copy)

        proxies_by_source[source.source_id] = source_entries

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

    return ProxyPoolResult(
        proxy_pool=proxy_pool,
        proxies_by_source=proxies_by_source,
        raw_to_final=raw_to_final,
    )


def match_filtered_rules_on_proxies(
    rules: list[FilteredRuleMatch],
    proxies_by_source: dict[str, list[dict[str, Any]]],
) -> list[str]:
    matched_names: list[str] = []
    for rule in rules:
        flags = re.IGNORECASE if "i" in rule.regex_flags else 0
        pattern = re.compile(rule.regex_pattern, flags)
        for proxy in proxies_by_source.get(rule.source_id, []):
            name = str(proxy.get("name", ""))
            raw_name = str(proxy.get("__raw_name", ""))
            if pattern.search(name) or pattern.search(raw_name):
                matched_names.append(name)

    return dedupe_keep_order(matched_names)


# ---------------------------------------------------------------------------
# Step 1: load_subscriptions (async — enqueues stale refreshes)
# ---------------------------------------------------------------------------

async def load_subscriptions(
    sub_ids_ordered: list[str],
    sub_map: dict[str, SubscriptionSource],
    diagnostics: GenerationDiagnosticsData,
) -> list[OrderedSource]:
    ordered_sources: list[OrderedSource] = []
    for source_id in sub_ids_ordered:
        sub = sub_map.get(source_id)
        if sub is None:
            diagnostics.warnings.append(f"subscription not found: {source_id}")
            continue
        if not sub.enabled:
            diagnostics.warnings.append(f"subscription disabled: {sub.name}")
            continue
        if sub.mode == "remote" and sub.auto_update and _is_stale(sub.next_refresh_at):
            diagnostics.stale_subscription_ids.append(sub.id)
            await refresh_loop_manager.enqueue_subscription_refresh(sub.id)
        if not sub.cached_proxies_json:
            raise GenerationError(f"subscription has no cached proxies: {sub.name}", 409)
        ordered_sources.append(
            OrderedSource(source_id=sub.id, source_name=sub.name, cached_proxies=sub.cached_proxies_json)
        )
    return ordered_sources


# ---------------------------------------------------------------------------
# Step 2: check_rule_staleness (async — enqueues stale refreshes)
# ---------------------------------------------------------------------------

async def check_rule_staleness(
    rule_map: dict[str, RuleSource],
    bindings: list[RouteBindingPayload],
    diagnostics: GenerationDiagnosticsData,
) -> None:
    for binding in sorted(bindings, key=lambda b: b.position):
        rule_source = rule_map.get(binding.rule_source_id)
        if rule_source is None:
            continue
        if rule_source.mode == "remote" and rule_source.auto_update and _is_stale(rule_source.next_refresh_at):
            if rule_source.id not in diagnostics.stale_rule_ids:
                diagnostics.stale_rule_ids.append(rule_source.id)
                await refresh_loop_manager.enqueue_rule_refresh(rule_source.id)


# ---------------------------------------------------------------------------
# Step 4: build_filtered_groups (pure)
# ---------------------------------------------------------------------------

def build_filtered_groups(ctx: GenerationContext) -> None:
    assert ctx.pool_result is not None
    sorted_fg = sorted(ctx.source.filtered_groups, key=lambda g: g.position)

    for fg in sorted_fg:
        fg_match_rules = [
            FilteredRuleMatch(
                source_id=r.subscription_source_id,
                regex_pattern=r.regex_pattern,
                regex_flags=r.regex_flags,
            )
            for r in sorted(fg.rules, key=lambda r: r.position)
        ]
        members = match_filtered_rules_on_proxies(fg_match_rules, ctx.pool_result.proxies_by_source)
        if not members:
            raise GenerationError(f"filtered group has no matched proxies: {fg.name}", 422)

        if fg.copy_nodes:
            used_names = {str(p.get("name", "")) for p in ctx.pool_result.proxy_pool}
            copy_members: list[str] = []
            proxy_by_name_snapshot = {str(p.get("name", "")): p for p in ctx.pool_result.proxy_pool}
            for original_name in members:
                original = proxy_by_name_snapshot.get(original_name)
                if original is None:
                    continue
                dup = copy.deepcopy(original)
                candidate = f"{original_name} [{fg.name}]"
                if candidate in used_names:
                    suffix = 2
                    while f"{candidate}#{suffix}" in used_names:
                        suffix += 1
                    candidate = f"{candidate}#{suffix}"
                dup["name"] = candidate
                dup["__raw_name"] = candidate
                used_names.add(candidate)
                ctx.pool_result.proxy_pool.append(dup)
                copy_members.append(candidate)
            members = copy_members

        ctx.filtered_group_members[fg.name] = members
        ctx.filtered_groups.append(
            _build_group_obj(fg.name, fg.group_mode, members, fg.test_url, fg.test_interval_sec)
        )

    ctx.group_names_filtered = [fg.name for fg in sorted_fg]


# ---------------------------------------------------------------------------
# Step 5: build_manual_groups (pure)
# ---------------------------------------------------------------------------

def build_manual_groups(ctx: GenerationContext) -> None:
    sorted_mg = sorted(ctx.source.manual_groups, key=lambda g: g.position)
    mg_by_name = {mg.name: mg for mg in sorted_mg}
    manual_resolved: dict[str, list[str]] = {}
    resolving: set[str] = set()

    def resolve_manual_group(name: str) -> list[str]:
        if name in manual_resolved:
            return manual_resolved[name]
        if name in resolving:
            raise GenerationError("manual group dependency cycle detected", 422)
        mg = mg_by_name.get(name)
        if mg is None:
            raise GenerationError(f"manual group not found: {name}", 422)
        resolving.add(name)
        members: list[str] = []
        for member in sorted(mg.members, key=lambda m: m.position):
            if member.member_type == "filtered_group":
                if member.member_ref not in ctx.filtered_group_members:
                    raise GenerationError(
                        f"manual group {name} references unknown filtered group {member.member_ref}", 422
                    )
                members.append(member.member_ref)
            elif member.member_type == "manual_group":
                _ = resolve_manual_group(member.member_ref)
                members.append(member.member_ref)
            else:
                raise GenerationError(f"invalid manual group member type: {member.member_type}", 422)
        members = dedupe_keep_order(members)
        if not members:
            raise GenerationError(f"manual group has no members: {name}", 422)
        manual_resolved[name] = members
        resolving.remove(name)
        return members

    for mg in sorted_mg:
        members = resolve_manual_group(mg.name)
        ctx.manual_groups.append(
            _build_group_obj(mg.name, mg.group_mode, members, mg.test_url, mg.test_interval_sec)
        )

    ctx.group_names_manual = [mg.name for mg in sorted_mg]
    ctx.available_non_route_groups = set(ctx.group_names_filtered + ctx.group_names_manual)


# ---------------------------------------------------------------------------
# Step 6: apply_dialer_overrides (pure)
# ---------------------------------------------------------------------------

def apply_dialer_overrides(ctx: GenerationContext) -> None:
    assert ctx.pool_result is not None
    proxy_by_name = {str(p.get("name", "")): p for p in ctx.pool_result.proxy_pool}
    matched_dialer_proxy_names: set[str] = set()

    for rule in ctx.source.dialer_override_rules:
        if rule.dialer_group_name not in ctx.available_non_route_groups:
            raise GenerationError(f"dialer group not found: {rule.dialer_group_name}", 422)
        if rule.filtered_group_name not in ctx.filtered_group_members:
            raise GenerationError(
                f"dialer references unknown filtered group: {rule.filtered_group_name}", 422
            )
        for proxy_name in ctx.filtered_group_members[rule.filtered_group_name]:
            if proxy_name not in matched_dialer_proxy_names:
                proxy = proxy_by_name.get(proxy_name)
                if proxy is not None:
                    proxy["dialer-proxy"] = rule.dialer_group_name
                    matched_dialer_proxy_names.add(proxy_name)


# ---------------------------------------------------------------------------
# Step 7: build_route_groups_and_rules (pure)
# ---------------------------------------------------------------------------

def build_route_groups_and_rules(ctx: GenerationContext, rule_map: dict[str, RuleSource]) -> None:
    provider_keys_used: set[str] = set()

    for idx, binding in enumerate(sorted(ctx.source.route_bindings, key=lambda s: s.position), start=1):
        if binding.default_group_name not in ctx.available_non_route_groups | {"DIRECT", "REJECT"}:
            raise GenerationError(f"route default group not found: {binding.default_group_name}", 422)

        rule_source = rule_map.get(binding.rule_source_id)
        if rule_source is None:
            raise GenerationError(f"rule source not found for binding {binding.binding_name}", 422)
        if not rule_source.enabled:
            raise GenerationError(f"rule source disabled for binding {binding.binding_name}", 422)
        if not rule_source.cached_payload_lines_json:
            raise GenerationError(f"rule source has no cache: {rule_source.name}", 409)

        route_group_members = dedupe_keep_order(
            [binding.default_group_name, "DIRECT"]
            + ctx.group_names_manual
            + ctx.group_names_filtered
            + ["REJECT"]
        )
        ctx.route_groups.append(
            ProxyGroupObj(name=binding.binding_name, type="select", proxies=route_group_members)
        )

        key_base = slugify_name(binding.binding_name).replace("-", "_")
        provider_key = key_base or f"rule_provider_{idx}"
        if provider_key in provider_keys_used:
            suffix = 2
            while f"{provider_key}_{suffix}" in provider_keys_used:
                suffix += 1
            provider_key = f"{provider_key}_{suffix}"
        provider_keys_used.add(provider_key)

        rule_url = (
            f"{ctx.source.public_base_url}{settings.api_prefix}/public/"
            f"rules/{rule_source.id}.yaml"
        )
        ctx.rule_providers[provider_key] = RuleProviderObj(
            type="http",
            behavior=rule_source.behavior,
            format="yaml",
            path=f"./rules/{rule_source.id}.yaml",
            url=rule_url,
            interval=rule_source.update_interval_sec,
        )

        line = f"RULE-SET,{provider_key},{binding.binding_name}"
        if binding.no_resolve:
            line += ",no-resolve"
        ctx.rules.append(line)


# ---------------------------------------------------------------------------
# Step 8: resolve_final_target (pure)
# ---------------------------------------------------------------------------

def resolve_final_target(source: GenerationInput, available_groups: set[str]) -> str:
    if source.final_target_type == "group":
        if not source.final_target_group_name:
            raise GenerationError("final target group is required", 422)
        if source.final_target_group_name not in available_groups:
            raise GenerationError(f"final target group not found: {source.final_target_group_name}", 422)
        return source.final_target_group_name
    elif source.final_target_type in {"DIRECT", "REJECT"}:
        return source.final_target_type
    else:
        raise GenerationError("invalid final target type", 422)


# ---------------------------------------------------------------------------
# Step 9: filter_and_clean_proxies (pure)
# ---------------------------------------------------------------------------

def filter_and_clean_proxies(
    pool_result: ProxyPoolResult,
    all_groups: list[ProxyGroupObj],
) -> list[dict[str, Any]]:
    all_group_names = {group.name for group in all_groups}
    referenced_proxy_names: set[str] = set()
    for group in all_groups:
        for member in group.proxies:
            if member not in {"DIRECT", "REJECT"} and member not in all_group_names:
                referenced_proxy_names.add(member)

    final_proxies: list[dict[str, Any]] = []
    for proxy in pool_result.proxy_pool:
        proxy_name = str(proxy.get("name", ""))
        if proxy_name in referenced_proxy_names:
            out = {k: v for k, v in proxy.items() if not k.startswith("__")}
            final_proxies.append(out)

    return final_proxies


# ---------------------------------------------------------------------------
# Step 10: merge_into_base_yaml (pure)
# ---------------------------------------------------------------------------

def merge_into_base_yaml(
    base_config_yaml: str,
    proxies: list[dict[str, Any]],
    proxy_groups: list[dict[str, Any]],
    rule_providers: dict[str, dict[str, Any]],
    rules: list[str],
) -> str:
    try:
        base = yaml.safe_load(base_config_yaml)
    except yaml.YAMLError as exc:
        raise GenerationError(f"base config yaml parse failed: {exc}", 422) from exc

    if base is None:
        base = {}
    if not isinstance(base, dict):
        raise GenerationError("base config YAML must be object", 422)

    base["proxies"] = proxies
    base["proxy-groups"] = proxy_groups
    base["rule-providers"] = rule_providers
    base["rules"] = rules

    return yaml.safe_dump(base, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# Orchestrator: _generate_from_loaded_data (pure, sync)
# ---------------------------------------------------------------------------

def _generate_from_loaded_data(
    source: GenerationInput,
    diagnostics: GenerationDiagnosticsData,
    ordered_sources: list[OrderedSource],
    rule_map: dict[str, RuleSource],
) -> GenerationResult:
    ctx = GenerationContext(source=source, diagnostics=diagnostics)
    ctx.pool_result = build_proxy_pool_with_collision_names(ordered_sources)
    build_filtered_groups(ctx)
    build_manual_groups(ctx)
    apply_dialer_overrides(ctx)
    build_route_groups_and_rules(ctx, rule_map)
    final_target = resolve_final_target(source, ctx.available_non_route_groups)
    ctx.rules.append(f"MATCH,{final_target}")
    all_groups = ctx.filtered_groups + ctx.manual_groups + ctx.route_groups
    final_proxies = filter_and_clean_proxies(ctx.pool_result, all_groups)
    proxy_group_dicts = [g.model_dump(exclude_none=True) for g in all_groups]
    rule_provider_dicts = {k: v.model_dump() for k, v in ctx.rule_providers.items()}
    rendered = merge_into_base_yaml(
        source.base_config_yaml, final_proxies, proxy_group_dicts, rule_provider_dicts, ctx.rules,
    )
    return GenerationResult(yaml=rendered, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# DB fetch helpers (async)
# ---------------------------------------------------------------------------

async def _fetch_subscriptions(
    db: AsyncSession,
    filtered_groups: list[FilteredGroupPayload],
) -> tuple[list[str], dict[str, SubscriptionSource]]:
    sub_ids_ordered: list[str] = []
    seen: set[str] = set()
    for group in sorted(filtered_groups, key=lambda g: g.position):
        for rule in sorted(group.rules, key=lambda r: r.position):
            if rule.subscription_source_id not in seen:
                sub_ids_ordered.append(rule.subscription_source_id)
                seen.add(rule.subscription_source_id)

    sub_map: dict[str, SubscriptionSource] = {}
    if sub_ids_ordered:
        result = await db.execute(
            select(SubscriptionSource).where(SubscriptionSource.id.in_(sub_ids_ordered))
        )
        sub_map = {item.id: item for item in result.scalars().all()}

    return sub_ids_ordered, sub_map


async def _fetch_rule_sources(
    db: AsyncSession,
    route_bindings: list[RouteBindingPayload],
) -> dict[str, RuleSource]:
    rule_ids = [rb.rule_source_id for rb in route_bindings]
    if not rule_ids:
        return {}
    result = await db.execute(select(RuleSource).where(RuleSource.id.in_(rule_ids)))
    return {item.id: item for item in result.scalars().all()}


# ---------------------------------------------------------------------------
# Public entry point (async)
# ---------------------------------------------------------------------------

async def generate_config_yaml(
    db: AsyncSession,
    source: GenerationInput,
) -> GenerationResult:
    diagnostics = GenerationDiagnosticsData(
        stale_subscription_ids=[],
        stale_rule_ids=[],
        warnings=[],
    )
    sub_ids_ordered, sub_map = await _fetch_subscriptions(db, source.filtered_groups)
    rule_map = await _fetch_rule_sources(db, source.route_bindings)
    ordered_sources = await load_subscriptions(sub_ids_ordered, sub_map, diagnostics)
    await check_rule_staleness(rule_map, source.route_bindings, diagnostics)
    return _generate_from_loaded_data(source, diagnostics, ordered_sources, rule_map)


async def render_rule_source_yaml(rule_source: RuleSource) -> str:
    if not rule_source.cached_payload_lines_json:
        raise GenerationError(f"rule source has no cached payload: {rule_source.name}", 409)

    content = {"payload": rule_source.cached_payload_lines_json}
    return yaml.safe_dump(content, allow_unicode=True, sort_keys=False)
