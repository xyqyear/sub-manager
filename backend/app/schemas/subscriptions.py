from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


class SubscriptionCreate(BaseModel):
    name: str
    mode: str
    enabled: bool = True

    remote_url: str | None = None
    remote_auth_header: str | None = None
    use_proxy: bool = False
    auto_update: bool = False
    update_interval_sec: int = 3600

    proxy_yaml_object_text: str | None = None


class SubscriptionUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None

    remote_url: str | None = None
    remote_auth_header: str | None = None
    use_proxy: bool | None = None
    auto_update: bool | None = None
    update_interval_sec: int | None = None

    proxy_yaml_object_text: str | None = None


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    mode: str
    enabled: bool

    remote_url: str | None
    remote_auth_header: str | None
    use_proxy: bool

    auto_update: bool
    update_interval_sec: int
    next_refresh_at: datetime | None
    last_refresh_at: datetime | None

    last_status: str
    last_error: str | None
    subscription_userinfo_raw: str | None
    subscription_userinfo_json: dict[str, int] | None

    cached_proxies_json: list[dict] | None
    created_at: datetime
    updated_at: datetime


class SubscriptionRefreshResponse(BaseModel):
    id: str
    status: str
    detail: str


def validate_subscription_mode(mode: str) -> str:
    if mode not in {"remote", "manual"}:
        raise ValueError("mode must be remote or manual")
    return mode


SubscriptionCreate._validate_mode = field_validator("mode")(validate_subscription_mode)
