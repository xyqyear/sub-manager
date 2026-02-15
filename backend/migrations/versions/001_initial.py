"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_source",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("remote_url", sa.Text, nullable=True),
        sa.Column("remote_auth_header", sa.Text, nullable=True),
        sa.Column("auto_update", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("update_interval_sec", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(16), nullable=False, server_default="never"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("subscription_userinfo_raw", sa.Text, nullable=True),
        sa.Column("subscription_userinfo_json", sa.JSON, nullable=True),
        sa.Column("cached_raw_yaml", sa.Text, nullable=True),
        sa.Column("cached_proxies_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "rule_source",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("behavior", sa.String(16), nullable=False),
        sa.Column("remote_url", sa.Text, nullable=True),
        sa.Column("auto_update", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("update_interval_sec", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(16), nullable=False, server_default="never"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("cached_payload_lines_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "main_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("base_config_yaml", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("final_target_type", sa.String(16), nullable=False, server_default="DIRECT"),
        sa.Column("final_target_group_name", sa.String(128), nullable=True),
        sa.Column("filtered_groups", sa.Text, nullable=False, server_default="[]"),
        sa.Column("manual_groups", sa.Text, nullable=False, server_default="[]"),
        sa.Column("dialer_override_rules", sa.Text, nullable=False, server_default="[]"),
        sa.Column("route_bindings", sa.Text, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("main_config")
    op.drop_table("rule_source")
    op.drop_table("subscription_source")
