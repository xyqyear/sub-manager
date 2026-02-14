from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import UtcDatetime

SourceMode = Literal["remote", "manual"]
RuleBehavior = Literal["classical", "domain", "ipcidr"]


class RuleCreate(BaseModel):
    name: str
    mode: SourceMode
    behavior: RuleBehavior
    enabled: bool = True

    remote_url: str | None = None
    auto_update: bool = False
    update_interval_sec: int = 3600

    payload_lines: list[str] | None = None


class RuleUpdate(BaseModel):
    name: str | None = None
    behavior: RuleBehavior | None = None
    enabled: bool | None = None

    remote_url: str | None = None
    auto_update: bool | None = None
    update_interval_sec: int | None = None

    payload_lines: list[str] | None = None


class RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    mode: SourceMode
    behavior: RuleBehavior
    enabled: bool

    remote_url: str | None
    auto_update: bool
    update_interval_sec: int
    next_refresh_at: UtcDatetime | None
    last_refresh_at: UtcDatetime | None

    last_status: str
    last_error: str | None
    cached_payload_lines_json: list[str] | None

    created_at: UtcDatetime
    updated_at: UtcDatetime


class RuleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    mode: SourceMode
    behavior: RuleBehavior
    enabled: bool

    remote_url: str | None
    auto_update: bool
    update_interval_sec: int
    next_refresh_at: UtcDatetime | None
    last_refresh_at: UtcDatetime | None

    last_status: str
    last_error: str | None
    cached_payload_lines_count: int | None

    created_at: UtcDatetime
    updated_at: UtcDatetime


class RuleRefreshResponse(BaseModel):
    id: str
    status: str
    detail: str
