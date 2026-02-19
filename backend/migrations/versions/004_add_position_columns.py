"""add position columns to top-level resources

Revision ID: 004
Revises: 003
Create Date: 2025-01-01 00:00:03.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ["subscription_source", "rule_source", "route_template", "main_config"]


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("position", sa.Integer, nullable=False, server_default="0"))

    _backfill_positions()


def _backfill_positions() -> None:
    conn = op.get_bind()
    for table in _TABLES:
        rows = conn.execute(
            sa.text(f"SELECT id FROM {table} ORDER BY created_at DESC")
        ).fetchall()
        for idx, row in enumerate(rows):
            conn.execute(
                sa.text(f"UPDATE {table} SET position = :pos WHERE id = :id"),
                {"pos": idx, "id": row[0]},
            )


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("position")
