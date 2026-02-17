"""hoist test_url and test_interval_sec to main_config

Revision ID: 003
Revises: 002
Create Date: 2025-01-01 00:00:02.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("main_config") as batch_op:
        batch_op.add_column(sa.Column("test_url", sa.Text, nullable=True))
        batch_op.add_column(sa.Column("test_interval_sec", sa.Integer, nullable=True))

    _extract_from_groups()


def _extract_from_groups() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, filtered_groups, manual_groups FROM main_config")
    ).fetchall()

    for row in rows:
        config_id, fg_raw, mg_raw = row
        fg = json.loads(fg_raw) if fg_raw else []
        mg = json.loads(mg_raw) if mg_raw else []

        test_url = None
        test_interval_sec = None
        for group in fg + mg:
            if test_url is None and group.get("test_url"):
                test_url = group["test_url"]
            if test_interval_sec is None and group.get("test_interval_sec"):
                test_interval_sec = group["test_interval_sec"]

        for group in fg:
            group.pop("test_url", None)
            group.pop("test_interval_sec", None)
        for group in mg:
            group.pop("test_url", None)
            group.pop("test_interval_sec", None)

        conn.execute(
            sa.text(
                "UPDATE main_config SET test_url = :tu, test_interval_sec = :ti, "
                "filtered_groups = :fg, manual_groups = :mg WHERE id = :cid"
            ),
            {
                "tu": test_url,
                "ti": test_interval_sec,
                "fg": json.dumps(fg),
                "mg": json.dumps(mg),
                "cid": config_id,
            },
        )


def downgrade() -> None:
    _push_to_groups()

    with op.batch_alter_table("main_config") as batch_op:
        batch_op.drop_column("test_url")
        batch_op.drop_column("test_interval_sec")


def _push_to_groups() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, test_url, test_interval_sec, filtered_groups, manual_groups FROM main_config")
    ).fetchall()

    for row in rows:
        config_id, test_url, test_interval_sec, fg_raw, mg_raw = row
        fg = json.loads(fg_raw) if fg_raw else []
        mg = json.loads(mg_raw) if mg_raw else []

        for group in fg:
            group["test_url"] = test_url
            group["test_interval_sec"] = test_interval_sec
        for group in mg:
            group["test_url"] = test_url
            group["test_interval_sec"] = test_interval_sec

        conn.execute(
            sa.text(
                "UPDATE main_config SET filtered_groups = :fg, manual_groups = :mg WHERE id = :cid"
            ),
            {
                "fg": json.dumps(fg),
                "mg": json.dumps(mg),
                "cid": config_id,
            },
        )
