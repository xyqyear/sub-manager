from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import UtcDatetime

SourceMode = Literal["remote", "manual"]


class SubscriptionCreate(BaseModel):
    name: str
    mode: SourceMode
    enabled: bool = True

    remote_url: str | None = None
    remote_auth_header: str | None = None
    auto_update: bool = False
    update_interval_sec: int = 3600

    proxy_yaml_object_text: str | None = None


class SubscriptionUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None

    remote_url: str | None = None
    remote_auth_header: str | None = None
    auto_update: bool | None = None
    update_interval_sec: int | None = None

    proxy_yaml_object_text: str | None = None


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    mode: SourceMode
    enabled: bool

    remote_url: str | None
    remote_auth_header: str | None

    auto_update: bool
    update_interval_sec: int
    next_refresh_at: UtcDatetime | None
    last_refresh_at: UtcDatetime | None

    last_status: str
    last_error: str | None
    subscription_userinfo_raw: str | None
    subscription_userinfo_json: dict[str, int] | None

    cached_proxies_json: list[dict[str, Any]] | None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    position: int


class SubscriptionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    mode: SourceMode
    enabled: bool

    remote_url: str | None
    remote_auth_header: str | None

    auto_update: bool
    update_interval_sec: int
    next_refresh_at: UtcDatetime | None
    last_refresh_at: UtcDatetime | None

    last_status: str
    last_error: str | None
    subscription_userinfo_raw: str | None
    subscription_userinfo_json: dict[str, int] | None

    cached_proxies_count: int | None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    position: int


class SubscriptionRefreshResponse(BaseModel):
    id: str
    status: str
    detail: str
