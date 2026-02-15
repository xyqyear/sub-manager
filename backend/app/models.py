from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import uuid

from pydantic import TypeAdapter
from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.schemas.configs import (
    DialerOverridePayload,
    FilteredGroupPayload,
    ManualGroupPayload,
    RouteBindingPayload,
    SlotMappingPayload,
)
from app.schemas.route_templates import (
    RouteTemplateBindingPayload,
    RouteTemplateSlotPayload,
)
from app.services.common import utc_now


class PydanticListType(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, model_type: type, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._adapter = TypeAdapter(list[model_type])  # type: ignore[valid-type]

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return "[]"
        return self._adapter.dump_json(value).decode()

    def process_result_value(self, value: Any, dialect: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, str):
            return self._adapter.validate_json(value)
        return self._adapter.validate_python(value)


class TZDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: Any, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class SubscriptionSource(Base, TimestampMixin):
    __tablename__ = "subscription_source"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # remote|manual
    remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_auth_header: Mapped[str | None] = mapped_column(Text, nullable=True)

    auto_update: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    update_interval_sec: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    next_refresh_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    last_status: Mapped[str] = mapped_column(String(16), default="never", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    subscription_userinfo_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    subscription_userinfo_json: Mapped[list[dict[str, int]] | dict[str, int] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    cached_raw_yaml: Mapped[str | None] = mapped_column(Text, nullable=True)
    cached_proxies_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)


class RuleSource(Base, TimestampMixin):
    __tablename__ = "rule_source"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # remote|manual
    behavior: Mapped[str] = mapped_column(String(16), nullable=False)  # classical|domain|ipcidr
    remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    auto_update: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    update_interval_sec: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    next_refresh_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    last_status: Mapped[str] = mapped_column(String(16), default="never", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    cached_payload_lines_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)


class MainConfig(Base, TimestampMixin):
    __tablename__ = "main_config"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    base_config_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    final_target_type: Mapped[str] = mapped_column(
        String(16),
        default="DIRECT",
        nullable=False,
    )  # DIRECT|REJECT|group
    final_target_group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    filtered_groups: Mapped[list[FilteredGroupPayload]] = mapped_column(
        PydanticListType(FilteredGroupPayload), default=list, nullable=False
    )
    manual_groups: Mapped[list[ManualGroupPayload]] = mapped_column(
        PydanticListType(ManualGroupPayload), default=list, nullable=False
    )
    dialer_override_rules: Mapped[list[DialerOverridePayload]] = mapped_column(
        PydanticListType(DialerOverridePayload), default=list, nullable=False
    )
    route_template_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    slot_mappings: Mapped[list[SlotMappingPayload]] = mapped_column(
        PydanticListType(SlotMappingPayload), default=list, nullable=False
    )


class RouteTemplate(Base, TimestampMixin):
    __tablename__ = "route_template"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    slots: Mapped[list[RouteTemplateSlotPayload]] = mapped_column(
        PydanticListType(RouteTemplateSlotPayload), default=list, nullable=False
    )
    bindings: Mapped[list[RouteTemplateBindingPayload]] = mapped_column(
        PydanticListType(RouteTemplateBindingPayload), default=list, nullable=False
    )
