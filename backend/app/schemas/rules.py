from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


ALLOWED_BEHAVIORS = {"classical", "domain", "ipcidr"}


class RuleCreate(BaseModel):
    name: str
    mode: str
    behavior: str
    enabled: bool = True

    remote_url: str | None = None
    auto_update: bool = False
    update_interval_sec: int = 3600

    payload_lines: list[str] | None = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in {"remote", "manual"}:
            raise ValueError("mode must be remote or manual")
        return value

    @field_validator("behavior")
    @classmethod
    def validate_behavior(cls, value: str) -> str:
        if value not in ALLOWED_BEHAVIORS:
            raise ValueError("behavior must be classical, domain, or ipcidr")
        return value


class RuleUpdate(BaseModel):
    name: str | None = None
    behavior: str | None = None
    enabled: bool | None = None

    remote_url: str | None = None
    auto_update: bool | None = None
    update_interval_sec: int | None = None

    payload_lines: list[str] | None = None

    @field_validator("behavior")
    @classmethod
    def validate_behavior(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in ALLOWED_BEHAVIORS:
            raise ValueError("behavior must be classical, domain, or ipcidr")
        return value


class RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    mode: str
    behavior: str
    enabled: bool

    remote_url: str | None
    auto_update: bool
    update_interval_sec: int
    next_refresh_at: datetime | None
    last_refresh_at: datetime | None

    last_status: str
    last_error: str | None
    cached_payload_lines_json: list[str] | None

    created_at: datetime
    updated_at: datetime


class RuleRefreshResponse(BaseModel):
    id: str
    status: str
    detail: str
