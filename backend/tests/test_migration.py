from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


def _get_alembic_config(db_path: Path) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    ini_path = backend_dir / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _create_old_schema(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    c.execute("""
        CREATE TABLE subscription_source (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(128) UNIQUE NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            mode VARCHAR(16) NOT NULL,
            remote_url TEXT,
            remote_auth_header TEXT,
            auto_update BOOLEAN NOT NULL DEFAULT 0,
            update_interval_sec INTEGER NOT NULL DEFAULT 3600,
            next_refresh_at DATETIME,
            last_refresh_at DATETIME,
            last_status VARCHAR(16) NOT NULL DEFAULT 'never',
            last_error TEXT,
            subscription_userinfo_raw TEXT,
            subscription_userinfo_json JSON,
            cached_raw_yaml TEXT,
            cached_proxies_json JSON,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE rule_source (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(128) UNIQUE NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            mode VARCHAR(16) NOT NULL,
            behavior VARCHAR(16) NOT NULL,
            remote_url TEXT,
            auto_update BOOLEAN NOT NULL DEFAULT 0,
            update_interval_sec INTEGER NOT NULL DEFAULT 3600,
            next_refresh_at DATETIME,
            last_refresh_at DATETIME,
            last_status VARCHAR(16) NOT NULL DEFAULT 'never',
            last_error TEXT,
            cached_payload_lines_json JSON,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE main_config (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(128) UNIQUE NOT NULL,
            base_config_yaml TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            final_target_type VARCHAR(16) NOT NULL DEFAULT 'DIRECT',
            final_target_group_name VARCHAR(128),
            filtered_groups TEXT NOT NULL DEFAULT '[]',
            manual_groups TEXT NOT NULL DEFAULT '[]',
            dialer_override_rules TEXT NOT NULL DEFAULT '[]',
            route_bindings TEXT NOT NULL DEFAULT '[]',
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
    """)

    c.execute(
        "INSERT INTO subscription_source (id, name, mode, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("sub-1", "Sub 1", "manual", now, now),
    )
    c.execute(
        "INSERT INTO rule_source (id, name, mode, behavior, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("rule-1", "Rule 1", "manual", "domain", now, now),
    )
    c.execute(
        "INSERT INTO rule_source (id, name, mode, behavior, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("rule-2", "Rule 2", "manual", "domain", now, now),
    )

    bindings_with_slots = json.dumps([
        {"position": 1, "binding_name": "Google", "rule_source_id": "rule-1", "default_group_name": "HK", "no_resolve": False},
        {"position": 2, "binding_name": "China", "rule_source_id": "rule-2", "default_group_name": "DIRECT", "no_resolve": True},
    ])
    c.execute(
        "INSERT INTO main_config (id, name, base_config_yaml, route_bindings, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("cfg-1", "Config 1", "mode: rule", bindings_with_slots, now, now),
    )

    c.execute(
        "INSERT INTO main_config (id, name, base_config_yaml, route_bindings, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("cfg-2", "Config Empty", "mode: rule", "[]", now, now),
    )

    direct_only = json.dumps([
        {"position": 1, "binding_name": "Ads", "rule_source_id": "rule-1", "default_group_name": "REJECT", "no_resolve": False},
    ])
    c.execute(
        "INSERT INTO main_config (id, name, base_config_yaml, route_bindings, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("cfg-3", "Config Direct Only", "mode: rule", direct_only, now, now),
    )

    conn.commit()
    conn.close()


@pytest.fixture
def migration_db(tmp_path):
    db_path = tmp_path / "test_migration.sqlite3"
    _create_old_schema(db_path)
    return db_path


def test_migration_002_creates_templates(migration_db):
    cfg = _get_alembic_config(migration_db)
    command.stamp(cfg, "001")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(migration_db))
    c = conn.cursor()

    tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "route_template" in tables

    templates = c.execute("SELECT id, name, slots, bindings FROM route_template").fetchall()
    template_by_name = {t[1]: t for t in templates}

    assert "Routes for Config 1" in template_by_name
    t1 = template_by_name["Routes for Config 1"]
    slots = json.loads(t1[2])
    assert len(slots) == 1
    assert slots[0]["name"] == "HK"

    bindings = json.loads(t1[3])
    assert len(bindings) == 2
    assert bindings[0]["binding_name"] == "Google"
    assert bindings[0]["default_target"] == "HK"
    assert bindings[1]["binding_name"] == "China"
    assert bindings[1]["default_target"] == "DIRECT"
    assert bindings[1]["no_resolve"] is True

    cfg1 = c.execute("SELECT route_template_id, slot_mappings FROM main_config WHERE id = 'cfg-1'").fetchone()
    assert cfg1[0] == t1[0]
    sm = json.loads(cfg1[1])
    assert len(sm) == 1
    assert sm[0]["slot_name"] == "HK"
    assert sm[0]["group_name"] == "HK"

    cfg2 = c.execute("SELECT route_template_id, slot_mappings FROM main_config WHERE id = 'cfg-2'").fetchone()
    assert cfg2[0] is None
    assert json.loads(cfg2[1]) == []

    assert "Routes for Config Direct Only" in template_by_name
    t3 = template_by_name["Routes for Config Direct Only"]
    slots3 = json.loads(t3[2])
    assert len(slots3) == 0

    columns = [row[1] for row in c.execute("PRAGMA table_info(main_config)").fetchall()]
    assert "route_bindings" not in columns
    assert "route_template_id" in columns
    assert "slot_mappings" in columns

    conn.close()
