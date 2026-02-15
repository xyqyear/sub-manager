"""add route templates

Revision ID: 002
Revises: 001
Create Date: 2025-01-01 00:00:01.000000
"""

from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "route_template",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("slots", sa.Text, nullable=False, server_default="[]"),
        sa.Column("bindings", sa.Text, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    with op.batch_alter_table("main_config") as batch_op:
        batch_op.add_column(sa.Column("route_template_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("slot_mappings", sa.Text, nullable=False, server_default="[]"))

    _migrate_route_bindings()

    with op.batch_alter_table("main_config") as batch_op:
        batch_op.drop_column("route_bindings")


def _migrate_route_bindings() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, name, route_bindings FROM main_config")
    ).fetchall()

    now = sa.func.now()

    for row in rows:
        config_id, config_name, route_bindings_raw = row
        bindings = json.loads(route_bindings_raw) if route_bindings_raw else []
        if not bindings:
            continue

        slot_names: list[str] = []
        seen_slots: set[str] = set()
        for b in bindings:
            target = b.get("default_group_name", "")
            if target not in ("DIRECT", "REJECT") and target not in seen_slots:
                slot_names.append(target)
                seen_slots.add(target)

        slots = [{"name": name, "position": i + 1} for i, name in enumerate(slot_names)]

        template_bindings = []
        for b in bindings:
            default_group = b.get("default_group_name", "")
            default_target = default_group if default_group in seen_slots else default_group
            template_bindings.append({
                "position": b.get("position", 0),
                "binding_name": b.get("binding_name", ""),
                "rule_source_id": b.get("rule_source_id", ""),
                "default_target": default_target,
                "no_resolve": b.get("no_resolve", False),
            })

        template_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO route_template (id, name, slots, bindings, created_at, updated_at) "
                "VALUES (:id, :name, :slots, :bindings, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": template_id,
                "name": f"Routes for {config_name}",
                "slots": json.dumps(slots),
                "bindings": json.dumps(template_bindings),
            },
        )

        slot_mappings = [{"slot_name": name, "group_name": name} for name in slot_names]
        conn.execute(
            sa.text(
                "UPDATE main_config SET route_template_id = :tid, slot_mappings = :sm WHERE id = :cid"
            ),
            {
                "tid": template_id,
                "sm": json.dumps(slot_mappings),
                "cid": config_id,
            },
        )


def downgrade() -> None:
    with op.batch_alter_table("main_config") as batch_op:
        batch_op.add_column(sa.Column("route_bindings", sa.Text, nullable=False, server_default="[]"))

    _reverse_migrate()

    with op.batch_alter_table("main_config") as batch_op:
        batch_op.drop_column("route_template_id")
        batch_op.drop_column("slot_mappings")

    op.drop_table("route_template")


def _reverse_migrate() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, route_template_id, slot_mappings FROM main_config")
    ).fetchall()

    for row in rows:
        config_id, template_id, slot_mappings_raw = row
        if not template_id:
            continue

        slot_mappings = json.loads(slot_mappings_raw) if slot_mappings_raw else []
        slot_map = {m["slot_name"]: m["group_name"] for m in slot_mappings}

        tmpl = conn.execute(
            sa.text("SELECT bindings FROM route_template WHERE id = :tid"),
            {"tid": template_id},
        ).fetchone()
        if not tmpl:
            continue

        template_bindings = json.loads(tmpl[0]) if tmpl[0] else []
        route_bindings = []
        for b in template_bindings:
            target = b.get("default_target", "")
            if target not in ("DIRECT", "REJECT"):
                target = slot_map.get(target, target)
            route_bindings.append({
                "position": b.get("position", 0),
                "binding_name": b.get("binding_name", ""),
                "rule_source_id": b.get("rule_source_id", ""),
                "default_group_name": target,
                "no_resolve": b.get("no_resolve", False),
            })

        conn.execute(
            sa.text("UPDATE main_config SET route_bindings = :rb WHERE id = :cid"),
            {"rb": json.dumps(route_bindings), "cid": config_id},
        )
