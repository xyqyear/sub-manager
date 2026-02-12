from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
    use_proxy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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
    cached_proxies_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)


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


class FilteredGroup(Base, TimestampMixin):
    __tablename__ = "filtered_group"
    __table_args__ = (
        UniqueConstraint("main_config_id", "name", name="uq_cfg_filtered_group_name"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    main_config_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("main_config.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    group_mode: Mapped[str] = mapped_column(String(16), default="select", nullable=False)
    test_url: Mapped[str] = mapped_column(Text, nullable=False)
    test_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False)


class FilteredGroupRule(Base, TimestampMixin):
    __tablename__ = "filtered_group_rule"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    filtered_group_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("filtered_group.id", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("subscription_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    regex_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    regex_flags: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ManualGroup(Base, TimestampMixin):
    __tablename__ = "manual_group"
    __table_args__ = (
        UniqueConstraint("main_config_id", "name", name="uq_cfg_manual_group_name"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    main_config_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("main_config.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    group_mode: Mapped[str] = mapped_column(String(16), default="select", nullable=False)
    test_url: Mapped[str] = mapped_column(Text, nullable=False)
    test_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False)


class ManualGroupMember(Base, TimestampMixin):
    __tablename__ = "manual_group_member"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    manual_group_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("manual_group.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )  # filtered_group|manual_group
    member_ref: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DialerOverrideRule(Base, TimestampMixin):
    __tablename__ = "dialer_override_rule"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    main_config_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("main_config.id", ondelete="CASCADE"),
        nullable=False,
    )
    filtered_group_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dialer_group_name: Mapped[str] = mapped_column(String(128), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ShuntBinding(Base, TimestampMixin):
    __tablename__ = "shunt_binding"
    __table_args__ = (
        UniqueConstraint("main_config_id", "binding_name", name="uq_cfg_shunt_name"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    main_config_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("main_config.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    binding_name: Mapped[str] = mapped_column(String(128), nullable=False)

    rule_source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rule_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    default_group_name: Mapped[str] = mapped_column(String(128), nullable=False)
    no_resolve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
