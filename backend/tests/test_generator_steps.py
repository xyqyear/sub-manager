from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_dummy.db")

from app.schemas.configs import (
    DialerOverridePayload,
    FilteredGroupPayload,
    FilteredGroupRulePayload,
    ManualGroupMemberPayload,
    ManualGroupPayload,
    RouteBindingPayload,
)
from app.services.common import GenerationError
from app.services.generator import (
    GenerationContext,
    GenerationDiagnosticsData,
    GenerationInput,
    GenerationResult,
    OrderedSource,
    ProxyGroupObj,
    ProxyPoolResult,
    _generate_from_loaded_data,
    _is_stale,
    apply_dialer_overrides,
    build_filtered_groups,
    build_manual_groups,
    build_proxy_pool_with_collision_names,
    build_route_groups_and_rules,
    check_rule_staleness,
    filter_and_clean_proxies,
    load_subscriptions,
    merge_into_base_yaml,
    resolve_final_target,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_diag() -> GenerationDiagnosticsData:
    return GenerationDiagnosticsData(stale_subscription_ids=[], stale_rule_ids=[], warnings=[])


class _FakeSub:
    def __init__(self, **kwargs: Any) -> None:
        self.id: str = kwargs.get("id", "sub-1")
        self.name: str = kwargs.get("name", "Sub 1")
        self.enabled: bool = kwargs.get("enabled", True)
        self.mode: str = kwargs.get("mode", "manual")
        self.auto_update: bool = kwargs.get("auto_update", False)
        self.next_refresh_at: datetime | None = kwargs.get("next_refresh_at")
        self.cached_proxies_json: list[dict[str, Any]] | None = kwargs.get(
            "cached_proxies_json",
            [{"name": "node-a", "type": "socks5", "server": "1.1.1.1", "port": 1080}],
        )


class _FakeRuleSource:
    def __init__(self, **kwargs: Any) -> None:
        self.id: str = kwargs.get("id", "rule-1")
        self.name: str = kwargs.get("name", "Rule 1")
        self.enabled: bool = kwargs.get("enabled", True)
        self.mode: str = kwargs.get("mode", "manual")
        self.behavior: str = kwargs.get("behavior", "domain")
        self.auto_update: bool = kwargs.get("auto_update", False)
        self.next_refresh_at: datetime | None = kwargs.get("next_refresh_at")
        self.update_interval_sec: int = kwargs.get("update_interval_sec", 3600)
        self.cached_payload_lines_json: list[str] | None = kwargs.get(
            "cached_payload_lines_json", [".example.com"],
        )


def _make_sub(**kwargs: Any) -> Any:
    return _FakeSub(**kwargs)


def _make_rule_source(**kwargs: Any) -> Any:
    return _FakeRuleSource(**kwargs)


def _make_source_input(**overrides: Any) -> GenerationInput:
    defaults: dict[str, Any] = dict(
        base_config_yaml="mixed-port: 7890\n",
        final_target_type="DIRECT",
        public_base_url="http://test:5678",
    )
    defaults.update(overrides)
    return GenerationInput(**defaults)


def _make_ctx(
    source: GenerationInput | None = None,
    pool_result: ProxyPoolResult | None = None,
    **overrides: Any,
) -> GenerationContext:
    ctx = GenerationContext(
        source=source or _make_source_input(),
        diagnostics=_make_diag(),
    )
    if pool_result is not None:
        ctx.pool_result = pool_result
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def _simple_pool(proxies: list[dict], source_id: str = "sub-1") -> ProxyPoolResult:
    sources = [OrderedSource(source_id=source_id, source_name="Sub 1", cached_proxies=proxies)]
    return build_proxy_pool_with_collision_names(sources)


# ---------------------------------------------------------------------------
# load_subscriptions
# ---------------------------------------------------------------------------

class TestLoadSubscriptions:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        sub = _make_sub()
        diag = _make_diag()
        result = await load_subscriptions(["sub-1"], {"sub-1": sub}, diag)
        assert len(result) == 1
        assert result[0].source_id == "sub-1"
        assert diag.warnings == []

    @pytest.mark.asyncio
    async def test_missing_subscription_warns(self):
        diag = _make_diag()
        result = await load_subscriptions(["missing-id"], {}, diag)
        assert result == []
        assert any("not found" in w for w in diag.warnings)

    @pytest.mark.asyncio
    async def test_disabled_subscription_warns(self):
        sub = _make_sub(enabled=False)
        diag = _make_diag()
        result = await load_subscriptions(["sub-1"], {"sub-1": sub}, diag)
        assert result == []
        assert any("disabled" in w for w in diag.warnings)

    @pytest.mark.asyncio
    async def test_stale_remote_enqueues_refresh(self):
        sub = _make_sub(
            mode="remote",
            auto_update=True,
            next_refresh_at=datetime.now(UTC) - timedelta(hours=1),
        )
        diag = _make_diag()
        with patch("app.services.generator.refresh_loop_manager") as mock_mgr:
            mock_mgr.enqueue_subscription_refresh = AsyncMock()
            result = await load_subscriptions(["sub-1"], {"sub-1": sub}, diag)
        assert "sub-1" in diag.stale_subscription_ids
        mock_mgr.enqueue_subscription_refresh.assert_awaited_once_with("sub-1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_no_cache_raises_409(self):
        sub = _make_sub(cached_proxies_json=None)
        diag = _make_diag()
        with pytest.raises(GenerationError) as exc_info:
            await load_subscriptions(["sub-1"], {"sub-1": sub}, diag)
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# check_rule_staleness
# ---------------------------------------------------------------------------

class TestCheckRuleStaleness:
    @pytest.mark.asyncio
    async def test_stale_rule_enqueues_refresh(self):
        rule = _make_rule_source(
            mode="remote",
            auto_update=True,
            next_refresh_at=datetime.now(UTC) - timedelta(hours=1),
        )
        binding = RouteBindingPayload(position=1, binding_name="R1", rule_source_id="rule-1", default_group_name="FG", no_resolve=False)
        diag = _make_diag()
        with patch("app.services.generator.refresh_loop_manager") as mock_mgr:
            mock_mgr.enqueue_rule_refresh = AsyncMock()
            await check_rule_staleness({"rule-1": rule}, [binding], diag)
        assert "rule-1" in diag.stale_rule_ids
        mock_mgr.enqueue_rule_refresh.assert_awaited_once_with("rule-1")

    @pytest.mark.asyncio
    async def test_fresh_rule_no_side_effects(self):
        rule = _make_rule_source(
            mode="remote",
            auto_update=True,
            next_refresh_at=datetime.now(UTC) + timedelta(hours=1),
        )
        binding = RouteBindingPayload(position=1, binding_name="R1", rule_source_id="rule-1", default_group_name="FG", no_resolve=False)
        diag = _make_diag()
        with patch("app.services.generator.refresh_loop_manager") as mock_mgr:
            mock_mgr.enqueue_rule_refresh = AsyncMock()
            await check_rule_staleness({"rule-1": rule}, [binding], diag)
        assert diag.stale_rule_ids == []
        mock_mgr.enqueue_rule_refresh.assert_not_awaited()


# ---------------------------------------------------------------------------
# build_filtered_groups
# ---------------------------------------------------------------------------

class TestBuildFilteredGroups:
    def test_happy_path(self):
        pool = _simple_pool([{"name": "hk-1", "type": "ss"}, {"name": "us-1", "type": "ss"}])
        source = _make_source_input(
            filtered_groups=[
                FilteredGroupPayload(
                    name="HK", position=1, group_mode="select",
                    rules=[FilteredGroupRulePayload(subscription_source_id="sub-1", regex_pattern="hk", regex_flags="i", position=1)],
                ),
            ],
        )
        ctx = _make_ctx(source=source, pool_result=pool)
        build_filtered_groups(ctx)
        assert len(ctx.filtered_groups) == 1
        assert ctx.filtered_groups[0].name == "HK"
        assert "hk-1" in ctx.filtered_group_members["HK"]

    def test_no_match_raises_422(self):
        pool = _simple_pool([{"name": "us-1", "type": "ss"}])
        source = _make_source_input(
            filtered_groups=[
                FilteredGroupPayload(
                    name="HK", position=1, group_mode="select",
                    rules=[FilteredGroupRulePayload(subscription_source_id="sub-1", regex_pattern="hk", regex_flags="", position=1)],
                ),
            ],
        )
        ctx = _make_ctx(source=source, pool_result=pool)
        with pytest.raises(GenerationError) as exc_info:
            build_filtered_groups(ctx)
        assert exc_info.value.status_code == 422

    def test_case_insensitive_flag(self):
        pool = _simple_pool([{"name": "HK-Node", "type": "ss"}])
        source = _make_source_input(
            filtered_groups=[
                FilteredGroupPayload(
                    name="HK", position=1, group_mode="select",
                    rules=[FilteredGroupRulePayload(subscription_source_id="sub-1", regex_pattern="hk-node", regex_flags="i", position=1)],
                ),
            ],
        )
        ctx = _make_ctx(source=source, pool_result=pool)
        build_filtered_groups(ctx)
        assert len(ctx.filtered_group_members["HK"]) == 1

    def test_multiple_sources(self):
        sources = [
            OrderedSource(source_id="s1", source_name="S1", cached_proxies=[{"name": "a", "type": "ss"}]),
            OrderedSource(source_id="s2", source_name="S2", cached_proxies=[{"name": "b", "type": "ss"}]),
        ]
        pool = build_proxy_pool_with_collision_names(sources)
        source = _make_source_input(
            filtered_groups=[
                FilteredGroupPayload(
                    name="All", position=1, group_mode="select",
                    rules=[
                        FilteredGroupRulePayload(subscription_source_id="s1", regex_pattern=".*", regex_flags="", position=1),
                        FilteredGroupRulePayload(subscription_source_id="s2", regex_pattern=".*", regex_flags="", position=2),
                    ],
                ),
            ],
        )
        ctx = _make_ctx(source=source, pool_result=pool)
        build_filtered_groups(ctx)
        assert len(ctx.filtered_group_members["All"]) == 2

    def test_copy_nodes_duplicates_proxies(self):
        pool = _simple_pool([{"name": "node-a", "type": "ss", "server": "1.1.1.1"}])
        source = _make_source_input(
            filtered_groups=[
                FilteredGroupPayload(
                    name="Relay", position=1, group_mode="select", copy_nodes=True,
                    rules=[FilteredGroupRulePayload(subscription_source_id="sub-1", regex_pattern=".*", regex_flags="", position=1)],
                ),
            ],
        )
        ctx = _make_ctx(source=source, pool_result=pool)
        build_filtered_groups(ctx)
        members = ctx.filtered_group_members["Relay"]
        assert len(members) == 1
        assert members[0] == "node-a [Relay]"
        assert ctx.pool_result is not None
        pool_names = [str(p.get("name", "")) for p in ctx.pool_result.proxy_pool]
        assert "node-a" in pool_names
        assert "node-a [Relay]" in pool_names

    def test_copy_nodes_name_collision(self):
        pool = _simple_pool([
            {"name": "node-a", "type": "ss"},
            {"name": "node-a [Relay]", "type": "ss"},
        ])
        source = _make_source_input(
            filtered_groups=[
                FilteredGroupPayload(
                    name="Relay", position=1, group_mode="select", copy_nodes=True,
                    rules=[FilteredGroupRulePayload(subscription_source_id="sub-1", regex_pattern="node-a$", regex_flags="", position=1)],
                ),
            ],
        )
        ctx = _make_ctx(source=source, pool_result=pool)
        build_filtered_groups(ctx)
        members = ctx.filtered_group_members["Relay"]
        assert len(members) == 1
        assert members[0] == "node-a [Relay]#2"


# ---------------------------------------------------------------------------
# build_manual_groups
# ---------------------------------------------------------------------------

class TestBuildManualGroups:
    def _ctx_with_fg(self, fg_names: list[str]) -> GenerationContext:
        source = _make_source_input()
        ctx = _make_ctx(source=source)
        for name in fg_names:
            ctx.filtered_group_members[name] = [f"{name}-proxy"]
        ctx.group_names_filtered = fg_names
        return ctx

    def test_simple_resolution(self):
        ctx = self._ctx_with_fg(["FG-A"])
        ctx.source = _make_source_input(
            manual_groups=[
                ManualGroupPayload(
                    name="MG-A", position=1, group_mode="select",
                    members=[ManualGroupMemberPayload(member_type="filtered_group", member_ref="FG-A", position=1)],
                ),
            ],
        )
        build_manual_groups(ctx)
        assert len(ctx.manual_groups) == 1
        assert ctx.manual_groups[0].proxies == ["FG-A"]

    def test_nested_manual_groups(self):
        ctx = self._ctx_with_fg(["FG-A"])
        ctx.source = _make_source_input(
            manual_groups=[
                ManualGroupPayload(
                    name="Inner", position=1, group_mode="select",
                    members=[ManualGroupMemberPayload(member_type="filtered_group", member_ref="FG-A", position=1)],
                ),
                ManualGroupPayload(
                    name="Outer", position=2, group_mode="select",
                    members=[ManualGroupMemberPayload(member_type="manual_group", member_ref="Inner", position=1)],
                ),
            ],
        )
        build_manual_groups(ctx)
        assert len(ctx.manual_groups) == 2
        assert ctx.manual_groups[1].proxies == ["Inner"]

    def test_cycle_detection(self):
        ctx = self._ctx_with_fg(["FG-A"])
        ctx.source = _make_source_input(
            manual_groups=[
                ManualGroupPayload(
                    name="A", position=1, group_mode="select",
                    members=[ManualGroupMemberPayload(member_type="manual_group", member_ref="B", position=1)],
                ),
                ManualGroupPayload(
                    name="B", position=2, group_mode="select",
                    members=[ManualGroupMemberPayload(member_type="manual_group", member_ref="A", position=1)],
                ),
            ],
        )
        with pytest.raises(GenerationError) as exc_info:
            build_manual_groups(ctx)
        assert "cycle" in exc_info.value.message

    def test_unknown_filtered_group_ref(self):
        ctx = self._ctx_with_fg([])
        ctx.source = _make_source_input(
            manual_groups=[
                ManualGroupPayload(
                    name="MG", position=1, group_mode="select",
                    members=[ManualGroupMemberPayload(member_type="filtered_group", member_ref="NOPE", position=1)],
                ),
            ],
        )
        with pytest.raises(GenerationError) as exc_info:
            build_manual_groups(ctx)
        assert exc_info.value.status_code == 422

    def test_empty_members(self):
        ctx = self._ctx_with_fg(["FG-A"])
        ctx.source = _make_source_input(
            manual_groups=[
                ManualGroupPayload(name="MG", position=1, group_mode="select", members=[]),
            ],
        )
        with pytest.raises(GenerationError) as exc_info:
            build_manual_groups(ctx)
        assert "no members" in exc_info.value.message


# ---------------------------------------------------------------------------
# apply_dialer_overrides
# ---------------------------------------------------------------------------

class TestApplyDialerOverrides:
    def _ctx_with_pool_and_fg(self) -> GenerationContext:
        pool = _simple_pool([{"name": "node-a", "type": "ss"}, {"name": "node-b", "type": "ss"}])
        source = _make_source_input(
            dialer_override_rules=[
                DialerOverridePayload(filtered_group_name="FG", dialer_group_name="FG"),
            ],
        )
        ctx = _make_ctx(source=source, pool_result=pool)
        ctx.filtered_group_members = {"FG": ["node-a", "node-b"]}
        ctx.group_names_filtered = ["FG"]
        ctx.available_non_route_groups = {"FG"}
        return ctx

    def test_happy_path(self):
        ctx = self._ctx_with_pool_and_fg()
        apply_dialer_overrides(ctx)
        assert ctx.pool_result is not None
        proxy_map = {str(p.get("name", "")): p for p in ctx.pool_result.proxy_pool}
        assert proxy_map["node-a"]["dialer-proxy"] == "FG"
        assert proxy_map["node-b"]["dialer-proxy"] == "FG"

    def test_unknown_dialer_group(self):
        pool = _simple_pool([{"name": "node-a", "type": "ss"}])
        source = _make_source_input(
            dialer_override_rules=[
                DialerOverridePayload(filtered_group_name="FG", dialer_group_name="NOPE"),
            ],
        )
        ctx = _make_ctx(source=source, pool_result=pool)
        ctx.filtered_group_members = {"FG": ["node-a"]}
        ctx.available_non_route_groups = {"FG"}
        with pytest.raises(GenerationError) as exc_info:
            apply_dialer_overrides(ctx)
        assert exc_info.value.status_code == 422

    def test_unknown_filtered_group(self):
        pool = _simple_pool([{"name": "node-a", "type": "ss"}])
        source = _make_source_input(
            dialer_override_rules=[
                DialerOverridePayload(filtered_group_name="NOPE", dialer_group_name="FG"),
            ],
        )
        ctx = _make_ctx(source=source, pool_result=pool)
        ctx.filtered_group_members = {"FG": ["node-a"]}
        ctx.available_non_route_groups = {"FG"}
        with pytest.raises(GenerationError) as exc_info:
            apply_dialer_overrides(ctx)
        assert exc_info.value.status_code == 422

    def test_first_match_wins(self):
        pool = _simple_pool([{"name": "node-a", "type": "ss"}])
        source = _make_source_input(
            dialer_override_rules=[
                DialerOverridePayload(filtered_group_name="FG1", dialer_group_name="FG1"),
                DialerOverridePayload(filtered_group_name="FG2", dialer_group_name="FG2"),
            ],
        )
        ctx = _make_ctx(source=source, pool_result=pool)
        ctx.filtered_group_members = {"FG1": ["node-a"], "FG2": ["node-a"]}
        ctx.available_non_route_groups = {"FG1", "FG2"}
        apply_dialer_overrides(ctx)
        assert ctx.pool_result is not None
        proxy_map = {str(p.get("name", "")): p for p in ctx.pool_result.proxy_pool}
        assert proxy_map["node-a"]["dialer-proxy"] == "FG1"


# ---------------------------------------------------------------------------
# build_route_groups_and_rules
# ---------------------------------------------------------------------------

class TestBuildRouteGroupsAndRules:
    def _base_ctx(self) -> tuple[GenerationContext, dict]:
        source = _make_source_input(
            config_id="cfg-1",
            route_bindings=[
                RouteBindingPayload(position=1, binding_name="Google", rule_source_id="rule-1", default_group_name="FG", no_resolve=False),
            ],
        )
        ctx = _make_ctx(source=source)
        ctx.group_names_filtered = ["FG"]
        ctx.group_names_manual = []
        ctx.available_non_route_groups = {"FG"}
        rule = _make_rule_source()
        return ctx, {"rule-1": rule}

    def test_happy_path(self):
        ctx, rule_map = self._base_ctx()
        build_route_groups_and_rules(ctx, rule_map)
        assert len(ctx.route_groups) == 1
        assert ctx.route_groups[0].name == "Google"
        assert len(ctx.rule_providers) == 1
        assert len(ctx.rules) == 1
        assert "RULE-SET" in ctx.rules[0]

    def test_missing_rule_source(self):
        ctx, _ = self._base_ctx()
        with pytest.raises(GenerationError) as exc_info:
            build_route_groups_and_rules(ctx, {})
        assert exc_info.value.status_code == 422

    def test_disabled_rule_source(self):
        ctx, rule_map = self._base_ctx()
        rule_map["rule-1"].enabled = False
        with pytest.raises(GenerationError) as exc_info:
            build_route_groups_and_rules(ctx, rule_map)
        assert exc_info.value.status_code == 422

    def test_no_cache(self):
        ctx, rule_map = self._base_ctx()
        rule_map["rule-1"].cached_payload_lines_json = None
        with pytest.raises(GenerationError) as exc_info:
            build_route_groups_and_rules(ctx, rule_map)
        assert exc_info.value.status_code == 409

    def test_no_resolve_flag(self):
        source = _make_source_input(
            config_id="cfg-1",
            route_bindings=[
                RouteBindingPayload(position=1, binding_name="China", rule_source_id="rule-1", default_group_name="DIRECT", no_resolve=True),
            ],
        )
        ctx = _make_ctx(source=source)
        ctx.group_names_filtered = []
        ctx.group_names_manual = []
        ctx.available_non_route_groups = set()
        rule = _make_rule_source()
        build_route_groups_and_rules(ctx, {"rule-1": rule})
        assert ctx.rules[0].endswith(",no-resolve")

    def test_provider_key_collision(self):
        source = _make_source_input(
            config_id="cfg-1",
            route_bindings=[
                RouteBindingPayload(position=1, binding_name="Google", rule_source_id="r1", default_group_name="DIRECT", no_resolve=False),
                RouteBindingPayload(position=2, binding_name="Google", rule_source_id="r2", default_group_name="DIRECT", no_resolve=False),
            ],
        )
        ctx = _make_ctx(source=source)
        ctx.available_non_route_groups = set()
        r1 = _make_rule_source(id="r1", name="R1")
        r2 = _make_rule_source(id="r2", name="R2")
        build_route_groups_and_rules(ctx, {"r1": r1, "r2": r2})
        keys = list(ctx.rule_providers.keys())
        assert len(keys) == 2
        assert keys[0] != keys[1]
        assert keys[1].endswith("_2")

    def test_route_group_member_order(self):
        source = _make_source_input(
            config_id="cfg-1",
            route_bindings=[
                RouteBindingPayload(position=1, binding_name="Route", rule_source_id="rule-1", default_group_name="MG", no_resolve=False),
            ],
        )
        ctx = _make_ctx(source=source)
        ctx.group_names_filtered = ["FG"]
        ctx.group_names_manual = ["MG"]
        ctx.available_non_route_groups = {"FG", "MG"}
        rule = _make_rule_source()
        build_route_groups_and_rules(ctx, {"rule-1": rule})
        members = ctx.route_groups[0].proxies
        # order: [default_group, DIRECT, manual..., filtered..., REJECT] deduped
        assert members[0] == "MG"
        assert members[1] == "DIRECT"
        assert "FG" in members
        assert "REJECT" in members
        assert members.index("DIRECT") < members.index("FG")
        assert members[-1] == "REJECT"
        assert len(members) == len(set(members))


# ---------------------------------------------------------------------------
# resolve_final_target
# ---------------------------------------------------------------------------

class TestResolveFinalTarget:
    def test_direct(self):
        source = _make_source_input(final_target_type="DIRECT")
        assert resolve_final_target(source, set()) == "DIRECT"

    def test_reject(self):
        source = _make_source_input(final_target_type="REJECT")
        assert resolve_final_target(source, set()) == "REJECT"

    def test_valid_group(self):
        source = _make_source_input(final_target_type="group", final_target_group_name="FG")
        assert resolve_final_target(source, {"FG"}) == "FG"

    def test_group_missing_name(self):
        source = _make_source_input(final_target_type="group", final_target_group_name=None)
        with pytest.raises(GenerationError) as exc_info:
            resolve_final_target(source, set())
        assert exc_info.value.status_code == 422

    def test_group_unknown_name(self):
        source = _make_source_input(final_target_type="group", final_target_group_name="NOPE")
        with pytest.raises(GenerationError) as exc_info:
            resolve_final_target(source, {"FG"})
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# filter_and_clean_proxies
# ---------------------------------------------------------------------------

class TestFilterAndCleanProxies:
    def test_strips_internal_keys(self):
        pool = _simple_pool([{"name": "node-a", "type": "ss", "server": "1.1.1.1"}])
        groups = [ProxyGroupObj(name="G", type="select", proxies=["node-a"])]
        result = filter_and_clean_proxies(pool, groups)
        assert len(result) == 1
        assert not any(k.startswith("__") for k in result[0])

    def test_only_referenced_proxies(self):
        pool = _simple_pool([
            {"name": "node-a", "type": "ss"},
            {"name": "node-b", "type": "ss"},
        ])
        groups = [ProxyGroupObj(name="G", type="select", proxies=["node-a"])]
        result = filter_and_clean_proxies(pool, groups)
        assert len(result) == 1
        assert result[0]["name"] == "node-a"

    def test_direct_reject_not_treated_as_proxy(self):
        pool = _simple_pool([{"name": "node-a", "type": "ss"}])
        groups = [ProxyGroupObj(name="G", type="select", proxies=["node-a", "DIRECT", "REJECT"])]
        result = filter_and_clean_proxies(pool, groups)
        assert len(result) == 1
        assert result[0]["name"] == "node-a"


# ---------------------------------------------------------------------------
# merge_into_base_yaml
# ---------------------------------------------------------------------------

class TestMergeIntoBaseYaml:
    def test_valid_merge(self):
        result = merge_into_base_yaml(
            "mixed-port: 7890\n",
            [{"name": "n", "type": "ss"}],
            [{"name": "G", "type": "select", "proxies": ["n"]}],
            {"rp": {"type": "http", "behavior": "domain"}},
            ["MATCH,DIRECT"],
        )
        parsed = yaml.safe_load(result)
        assert "proxies" in parsed
        assert "proxy-groups" in parsed
        assert "rule-providers" in parsed
        assert "rules" in parsed
        assert parsed["mixed-port"] == 7890

    def test_empty_base(self):
        result = merge_into_base_yaml("", [], [], {}, ["MATCH,DIRECT"])
        parsed = yaml.safe_load(result)
        assert parsed["proxies"] == []
        assert parsed["rules"] == ["MATCH,DIRECT"]

    def test_invalid_yaml(self):
        with pytest.raises(GenerationError) as exc_info:
            merge_into_base_yaml("{{invalid", [], [], {}, [])
        assert exc_info.value.status_code == 422

    def test_non_dict_yaml(self):
        with pytest.raises(GenerationError) as exc_info:
            merge_into_base_yaml("- item1\n- item2\n", [], [], {}, [])
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# Integration: _generate_from_loaded_data
# ---------------------------------------------------------------------------

class TestGenerateFromLoadedData:
    def test_full_pipeline(self):
        ordered_sources = [
            OrderedSource(source_id="s1", source_name="Sub1", cached_proxies=[
                {"name": "node-a", "type": "socks5", "server": "1.1.1.1", "port": 1080},
            ]),
        ]
        rule = _make_rule_source(id="r1")
        source = _make_source_input(
            config_id="cfg-1",
            filtered_groups=[
                FilteredGroupPayload(
                    name="FG", position=1, group_mode="select",
                    rules=[FilteredGroupRulePayload(subscription_source_id="s1", regex_pattern=".*", regex_flags="", position=1)],
                ),
            ],
            manual_groups=[
                ManualGroupPayload(
                    name="MG", position=1, group_mode="select",
                    members=[ManualGroupMemberPayload(member_type="filtered_group", member_ref="FG", position=1)],
                ),
            ],
            route_bindings=[
                RouteBindingPayload(position=1, binding_name="Route", rule_source_id="r1", default_group_name="FG", no_resolve=False),
            ],
        )
        diag = _make_diag()
        result = _generate_from_loaded_data(source, diag, ordered_sources, {"r1": rule})
        assert isinstance(result, GenerationResult)
        parsed = yaml.safe_load(result.yaml)
        assert "proxies" in parsed
        assert "proxy-groups" in parsed
        assert any("MATCH,DIRECT" in r for r in parsed["rules"])

    def test_copy_nodes_with_dialer_override(self):
        ordered_sources = [
            OrderedSource(source_id="s1", source_name="Sub1", cached_proxies=[
                {"name": "shared", "type": "socks5", "server": "1.1.1.1", "port": 1080},
            ]),
        ]
        rule = _make_rule_source(id="r1")
        source = _make_source_input(
            config_id="cfg-1",
            filtered_groups=[
                FilteredGroupPayload(
                    name="Direct", position=1, group_mode="select", copy_nodes=False,
                    rules=[FilteredGroupRulePayload(subscription_source_id="s1", regex_pattern=".*", regex_flags="", position=1)],
                ),
                FilteredGroupPayload(
                    name="Relay", position=2, group_mode="select", copy_nodes=True,
                    rules=[FilteredGroupRulePayload(subscription_source_id="s1", regex_pattern=".*", regex_flags="", position=1)],
                ),
            ],
            dialer_override_rules=[
                DialerOverridePayload(filtered_group_name="Relay", dialer_group_name="Direct"),
            ],
            route_bindings=[
                RouteBindingPayload(position=1, binding_name="Route", rule_source_id="r1", default_group_name="Direct", no_resolve=False),
            ],
        )
        diag = _make_diag()
        result = _generate_from_loaded_data(source, diag, ordered_sources, {"r1": rule})
        parsed = yaml.safe_load(result.yaml)
        proxy_map = {p["name"]: p for p in parsed["proxies"]}
        assert "shared" in proxy_map
        assert "shared [Relay]" in proxy_map
        assert "dialer-proxy" not in proxy_map["shared"]
        assert proxy_map["shared [Relay]"]["dialer-proxy"] == "Direct"


# ---------------------------------------------------------------------------
# _is_stale: naive vs aware datetime regression
# ---------------------------------------------------------------------------

class TestIsStale:
    def test_none_is_not_stale(self):
        assert _is_stale(None) is False

    def test_aware_past_is_stale(self):
        assert _is_stale(datetime.now(UTC) - timedelta(hours=1)) is True

    def test_aware_future_is_not_stale(self):
        assert _is_stale(datetime.now(UTC) + timedelta(hours=1)) is False

    def test_naive_past_does_not_crash(self):
        naive = datetime(2000, 1, 1)
        assert _is_stale(naive) is True

    def test_naive_future_does_not_crash(self):
        naive = datetime(2099, 1, 1)
        assert _is_stale(naive) is False
