from __future__ import annotations

from datetime import datetime
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
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.schemas.configs import (
    DialerOverridePayload,
    FilteredGroupPayload,
    ManualGroupPayload,
    ShuntBindingPayload,
)


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


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
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
    next_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    next_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    password_plain: Mapped[str] = mapped_column(Text, nullable=False)
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
    shunt_bindings: Mapped[list[ShuntBindingPayload]] = mapped_column(
        PydanticListType(ShuntBindingPayload), default=list, nullable=False
    )
