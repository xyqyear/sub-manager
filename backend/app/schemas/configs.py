from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import UtcDatetime


FinalTargetType = Literal["DIRECT", "REJECT", "group"]
GroupMode = Literal["select", "fallback", "url-test"]
MemberType = Literal["filtered_group", "manual_group"]


class SlotMappingPayload(BaseModel):
    slot_name: str
    group_name: str


class MainConfigCreate(BaseModel):
    name: str
    base_config_yaml: str
    enabled: bool = True
    final_target_type: FinalTargetType = "DIRECT"
    final_target_group_name: str | None = None
    test_url: str | None = None
    test_interval_sec: int | None = None
    filtered_groups: list[FilteredGroupPayload] = []
    manual_groups: list[ManualGroupPayload] = []
    dialer_override_rules: list[DialerOverridePayload] = []
    route_template_id: str | None = None
    slot_mappings: list[SlotMappingPayload] = []


class MainConfigUpdate(BaseModel):
    name: str | None = None
    base_config_yaml: str | None = None
    enabled: bool | None = None
    final_target_type: FinalTargetType | None = None
    final_target_group_name: str | None = None
    test_url: str | None = None
    test_interval_sec: int | None = None
    filtered_groups: list[FilteredGroupPayload] | None = None
    manual_groups: list[ManualGroupPayload] | None = None
    dialer_override_rules: list[DialerOverridePayload] | None = None
    route_template_id: str | None = None
    slot_mappings: list[SlotMappingPayload] | None = None


class MainConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_config_yaml: str
    enabled: bool
    final_target_type: str
    final_target_group_name: str | None
    test_url: str | None
    test_interval_sec: int | None
    filtered_groups: list[FilteredGroupPayload]
    manual_groups: list[ManualGroupPayload]
    dialer_override_rules: list[DialerOverridePayload]
    route_template_id: str | None
    slot_mappings: list[SlotMappingPayload]
    created_at: UtcDatetime
    updated_at: UtcDatetime
    position: int


class FilteredGroupRulePayload(BaseModel):
    subscription_source_id: str
    regex_pattern: str
    regex_flags: str = ""
    position: int


class FilteredGroupPayload(BaseModel):
    name: str
    position: int
    group_mode: GroupMode
    copy_nodes: bool = False
    rules: list[FilteredGroupRulePayload]


class ManualGroupMemberPayload(BaseModel):
    member_type: MemberType
    member_ref: str
    position: int


class ManualGroupPayload(BaseModel):
    name: str
    position: int
    group_mode: GroupMode
    members: list[ManualGroupMemberPayload]


class DialerOverridePayload(BaseModel):
    filtered_group_name: str
    dialer_group_name: str


class RouteBindingPayload(BaseModel):
    position: int
    binding_name: str
    rule_source_id: str
    default_group_name: str
    no_resolve: bool = False


class FilteredGroupPreviewRulePayload(BaseModel):
    subscription_source_id: str | None = None
    regex_pattern: str | None = None
    regex_flags: str = ""
    position: int | None = None


class FilteredGroupPreviewGroupPayload(BaseModel):
    name: str | None = None
    rules: list[FilteredGroupPreviewRulePayload] = []


class FilteredGroupPreviewRequest(BaseModel):
    filtered_groups: list[FilteredGroupPreviewGroupPayload] = []


class FilteredGroupPreviewRuleResult(BaseModel):
    matched_proxy_names: list[str]
    issue: str | None = None


class FilteredGroupPreviewItem(BaseModel):
    name: str
    rule_results: list[FilteredGroupPreviewRuleResult]


class FilteredGroupPreviewResponse(BaseModel):
    groups: list[FilteredGroupPreviewItem]


class AdminHealthResponse(BaseModel):
    status: str
    refresh_loop_running: bool


class GenerationDiagnostics(BaseModel):
    stale_subscription_ids: list[str]
    stale_rule_ids: list[str]
    warnings: list[str]


class PreviewWithDiagnosticsResponse(BaseModel):
    yaml: str
    diagnostics: GenerationDiagnostics


class DraftPreviewRequest(BaseModel):
    base_config_yaml: str
    final_target_type: FinalTargetType = "DIRECT"
    final_target_group_name: str | None = None
    config_id: str | None = None
    test_url: str | None = None
    test_interval_sec: int | None = None
    filtered_groups: list[FilteredGroupPayload] = []
    manual_groups: list[ManualGroupPayload] = []
    dialer_override_rules: list[DialerOverridePayload] = []
    route_template_id: str | None = None
    slot_mappings: list[SlotMappingPayload] = []
