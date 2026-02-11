from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


FinalTargetType = Literal["DIRECT", "REJECT", "group"]
GroupMode = Literal["select", "fallback", "url-test"]
MemberType = Literal["filtered_group", "manual_group", "proxy_name"]


class MainConfigCreate(BaseModel):
    name: str
    password_plain: str
    base_config_yaml: str
    enabled: bool = True
    final_target_type: FinalTargetType = "DIRECT"
    final_target_group_name: str | None = None


class MainConfigUpdate(BaseModel):
    name: str | None = None
    password_plain: str | None = None
    base_config_yaml: str | None = None
    enabled: bool | None = None
    final_target_type: FinalTargetType | None = None
    final_target_group_name: str | None = None


class MainConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    password_plain: str
    base_config_yaml: str
    enabled: bool
    final_target_type: str
    final_target_group_name: str | None
    created_at: datetime
    updated_at: datetime


class MainConfigSubscriptionLinkPayload(BaseModel):
    subscription_source_id: str
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
    test_url: str | None = None
    test_interval_sec: int | None = None
    rules: list[FilteredGroupRulePayload]


class ManualGroupMemberPayload(BaseModel):
    member_type: MemberType
    member_ref: str
    position: int


class ManualGroupPayload(BaseModel):
    name: str
    position: int
    group_mode: GroupMode
    test_url: str | None = None
    test_interval_sec: int | None = None
    members: list[ManualGroupMemberPayload]


class DialerOverridePayload(BaseModel):
    match_regex: str
    dialer_group_name: str
    position: int


class ShuntBindingPayload(BaseModel):
    position: int
    binding_name: str
    rule_source_id: str
    default_group_name: str
    no_resolve: bool = False


class BuilderPayload(BaseModel):
    subscription_links: list[MainConfigSubscriptionLinkPayload]
    filtered_groups: list[FilteredGroupPayload]
    manual_groups: list[ManualGroupPayload]
    dialer_override_rules: list[DialerOverridePayload]
    shunt_bindings: list[ShuntBindingPayload]


class BuilderRead(BaseModel):
    subscription_links: list[MainConfigSubscriptionLinkPayload]
    filtered_groups: list[FilteredGroupPayload]
    manual_groups: list[ManualGroupPayload]
    dialer_override_rules: list[DialerOverridePayload]
    shunt_bindings: list[ShuntBindingPayload]


class PreviewResponse(BaseModel):
    yaml: str
    diagnostics: list[str]


class PublicArtifactQuery(BaseModel):
    password: str


class AdminHealthResponse(BaseModel):
    status: str
    refresh_loop_running: bool


class RulePayloadResponse(BaseModel):
    yaml: str


class GenerationDiagnostics(BaseModel):
    stale_subscription_ids: list[str]
    stale_rule_ids: list[str]
    warnings: list[str]


class PreviewWithDiagnosticsResponse(BaseModel):
    yaml: str
    diagnostics: GenerationDiagnostics


class PasswordQuery(BaseModel):
    password: str
