# Sub Manager

Clash Meta proxy subscription / routing rule management and config generation tool.

## Working with This Document

This file is a reference for the project's architecture, domain model, API surface, and known gaps. When exiting plan mode, update this document to reflect any structural changes introduced by the plan — add new fields, routes, or components; remove deleted ones; adjust descriptions as needed. Do not write changelogs or "updated X" notes; keep the document self-consistent as if it were written from scratch for the current state of the codebase.

## Quick Start

```bash
# backend (from backend/)
uv run python main.py          # starts on :5678

# frontend (from frontend/)
pnpm dev                        # starts on :3000, proxies /api -> :5678

# tests
cd backend && uv run pytest
```

Set `ADMIN_TOKEN` in `backend/.env` (defaults to `change-me`). Use same token to log in on the frontend.

## Product Overview

### Problem

Clash Meta users who subscribe to multiple proxy providers need to:
- Combine proxy nodes from different providers into one config
- Apply traffic routing rules (e.g., Google traffic through HK nodes, domestic traffic direct)
- Keep subscriptions and rules auto-updated
- Produce a single YAML config URL that Clash Meta can consume

Sub Manager solves this with a web UI where users manage their sources and visually compose configs.

### Core Workflow

Three stages, each corresponding to a resource type:

**Stage 1 — Subscription Sources: where proxy nodes come from**

Users add their proxy providers. A provider can be:
- A remote URL (e.g., from a VPN service) — the system fetches and caches the proxy node list, tracks traffic usage/expiry, and auto-refreshes on a schedule
- A manually entered single proxy node (YAML)

Each source provides a list of proxy nodes (e.g., "Hong Kong 1", "US IEPL 2", etc.).

**Stage 2 — Rule Sources: traffic routing rules**

Users add rule sets that define which domains/IPs should be matched. A rule source can be:
- A remote URL (e.g., a community-maintained list of ad domains or China IP ranges)
- Manually entered rules

Each rule source has a behavior type: `classical` (full rule syntax), `domain` (domain lists), or `ipcidr` (IP ranges). The system caches rule payloads locally and serves them from its own URL in the generated config.

**Stage 3 — Main Configs: the composition layer**

This is where everything comes together. A main config has:
- A base YAML (ports, DNS, TUN settings, etc. — everything except proxies, groups, and rules)
- Four builder field groups (filtered groups, manual groups, dialer overrides, shunt bindings) that visually compose proxy groups and routing rules (see below)
- A password for public access

### The Builder

The builder is the core of the product. It has four sections that work together to produce the `proxies`, `proxy-groups`, `rule-providers`, and `rules` sections of the final Clash Meta config.

**Filtered Groups** — "Give me specific nodes from a subscription"

Each filtered group defines regex rules against one or more subscription sources. Example:
- Name: "HK", regex `香港|HK|Hong Kong` against subscription "Provider A" → produces a proxy group containing only matching HK nodes
- Mode: `select` (manual pick), `url-test` (auto-select fastest), or `fallback` (auto-failover)

Only nodes matched by at least one filtered group appear in the final config. Unmatched nodes are excluded entirely.

**Manual Groups** — "Combine groups for advanced routing"

Manual groups reference filtered groups or other manual groups as members. Use cases:
- A "Node Select" group containing "HK", "JP", "US" filtered groups plus an "Auto Select" url-test group
- A load-balancing or failover group across multiple regions

**Dialer Overrides** — "Route traffic through a proxy chain"

Assigns a `dialer-proxy` to all nodes in a filtered group, creating a relay chain. Example:
- All nodes in "My VPS" group get `dialer-proxy: "US Transit"` → traffic goes: client → US Transit node → VPS node → destination
- This hides the final destination from the transit provider and hides the transit from the destination

**Shunt Bindings** — "Which rule goes to which group"

Each binding pairs a rule source with a proxy group name and a default target. Example:
- Rule "Google" → group "Google", default to "Node Select"
- Rule "Ad Block" → group "Ads", default to REJECT
- Rule "China" → group "Domestic", default to DIRECT

The order of shunt bindings determines rule matching priority in the generated config. A final implicit MATCH rule catches all remaining traffic, directed to DIRECT, REJECT, or a chosen group.

Each shunt binding generates a `select`-type proxy group whose members are: `[default_group, DIRECT, REJECT] + all manual groups + all filtered groups`, allowing the user to override the default at runtime in Clash Meta.

### Output

The system generates a complete Clash Meta YAML config accessible via a password-protected public URL. Clash Meta clients subscribe to this URL. When subscriptions or rules refresh, the generated config automatically reflects the latest data.

Rule payloads referenced in the config's `rule-providers` section point back to this server's own URLs (not the original remote URLs), so the system acts as a caching proxy for rules.

## Tech Stack

| Layer    | Stack                                                  |
|----------|--------------------------------------------------------|
| Backend  | FastAPI + async SQLAlchemy + aiosqlite, Python >= 3.13 |
| Frontend | React 19 + Vite 7 + Ant Design 6 + TypeScript 5.9     |
| Database | SQLite (single file `backend/db.sqlite3`)              |
| Auth     | Static bearer token (admin), per-config password (public) |

## Repository Layout

```
backend/
  main.py                          # dev entrypoint (uvicorn, port 5678, reload)
  app/
    main.py                        # FastAPI app factory, lifespan, router mounting
    config.py                      # pydantic-settings (env-driven)
    auth.py                        # bearer token dependency
    models.py                      # SQLAlchemy ORM models
    db/database.py                 # async engine/session, init_db()
    routers/admin/                 # admin CRUD APIs (bearer protected)
      health.py                    # GET /api/admin/health
      subscriptions.py             # subscription CRUD + refresh
      rules.py                     # rule CRUD + refresh
      main_configs.py              # config CRUD + preview + filtered-group-preview
    routers/public/
      configs.py                   # public artifact + rule-payload fetch (password protected)
    schemas/                       # pydantic request/response models
      subscriptions.py
      rules.py
      configs.py                   # MainConfigCreate/Update/Read, DraftPreviewRequest, PreviewWithDiagnosticsResponse, etc.
    services/                      # business logic
      common.py                    # ServiceError, GenerationError, jitter, slugify, parsing
      subscriptions.py             # subscription CRUD + remote fetch + cache
      rules.py                     # rule CRUD + remote fetch + validation
      main_configs.py              # config CRUD + validation
      generator.py                 # YAML assembly engine
      refresh_loop.py              # in-process async background refresh
  tests/
    conftest.py                    # test DB isolation (/tmp/sub_manager_test.sqlite3)
    test_admin_auth.py
    test_parsers.py
    test_generation_flow.py

frontend/
  vite.config.ts                   # port 3000, /api proxy -> :5678, @ alias -> src/
  src/
    main.tsx                       # app bootstrap, Ant Design theme, router
    App.tsx                        # shell, guarded routing, navigation
    utils/api.ts                   # axios instance + bearer interceptor + token storage
    types/api.ts                   # TS interfaces matching backend schemas
    pages/
      Login.tsx
      Subscriptions.tsx            # subscription CRUD UI
      Rules.tsx                    # rule CRUD UI
      MainConfigs.tsx              # config list + editor integration
      main-configs/
        MainConfigEditorDrawer.tsx # visual builder editor (all builder sections)

references/                        # NOT runtime code, for context only
  requirements.md                  # product requirements + TODO list (Chinese)
  DEVELOPMENT.md                   # full technical documentation
  reference_yaml.yaml              # target Clash Meta config output format
  reference_frontend.html          # UI layout reference (different library, don't copy)
  profile.ts                       # mihomo.party source showing fetch headers/parsing
```

## Domain Model

The three resource types described in the Product Overview map to the following database tables and fields.

### Subscription Sources (`subscription_source`)

Corresponds to Stage 1 (proxy node providers). Two modes:
- **remote**: Fetched from URL with `User-Agent: mihomo/1.18.3`, optional `Authorization` header. Caches `proxies` list from YAML. Parses `subscription-userinfo` header for traffic data.
- **manual**: User provides a single YAML proxy object directly.

Fields: `id`, `name` (unique), `mode`, `enabled`, `remote_url`, `remote_auth_header`, `auto_update`, `update_interval_sec`, `next_refresh_at`, `last_status` (never/ok/error), `cached_proxies_json`.

### Rule Sources (`rule_source`)

Corresponds to Stage 2 (traffic routing rules). Two modes (remote/manual). Each has a `behavior`: `classical`, `domain`, or `ipcidr`. Cached as `payload_lines` (list of strings). Only YAML format supported.

### Main Configs (`main_config`) + Builder Graph

Corresponds to Stage 3 (the composition layer). A main config combines subscriptions + rules into a final output. Each config has:
- `base_config_yaml`: base Clash settings (ports, DNS, TUN, etc.)
- `password_plain`: per-config access password for public endpoints
- `final_target_type`: DIRECT / REJECT / group (for the trailing MATCH rule)
- A **builder graph** stored as 4 JSON columns directly on `main_config`, using a `PydanticListType` TypeDecorator that serializes/deserializes via Pydantic `TypeAdapter`:

| Column                 | Pydantic Type              | Purpose                                    |
|------------------------|----------------------------|--------------------------------------------|
| `filtered_groups`      | `list[FilteredGroupPayload]` | Named proxy groups filtered by regex (each contains nested rules) |
| `manual_groups`        | `list[ManualGroupPayload]`   | Named groups referencing filtered/manual groups (each contains nested members) |
| `dialer_override_rules`| `list[DialerOverridePayload]`| Assigns `dialer-proxy` to proxies in a filtered group |
| `shunt_bindings`       | `list[ShuntBindingPayload]`  | Binds a rule source to a shunt proxy-group |

All IDs are UUID strings (36 chars). All tables have `created_at`/`updated_at` timestamps. Lists are ordered by `position` field within the JSON arrays.

## Config Generation Engine (`services/generator.py`)

The generation pipeline uses a single `GenerationInput` model and `generate_config_yaml()` entry point for both saved configs and draft previews. Callers construct `GenerationInput` from either a `MainConfig` ORM object or a `DraftPreviewRequest` schema.

1. **Fetch subscriptions** - `_fetch_subscriptions()` derives subscription IDs from filtered group rules (first-seen order), fetches `SubscriptionSource` rows from DB.
2. **Fetch rule sources** - `_fetch_rule_sources()` fetches `RuleSource` rows referenced by shunt bindings.
3. **Load subscriptions** - Gather cached proxies. Skip disabled (with warning). Fail on missing cache (409).
4. **Name collision resolution** - Raw name -> `raw@source_slug` -> `raw@source_slug#N` if still colliding.
5. **Filtered groups** - Apply regex rules against source proxies. Match checks both final and raw names. Empty match = error (422). Group modes: `select`, `fallback`, `url-test`.
6. **Manual groups** - Recursive resolution. Members can be filtered groups or other manual groups. Cycle detection at runtime.
7. **Dialer overrides** - Each rule targets a filtered group and assigns `dialer-proxy` to all proxies in that group. First-match-wins per proxy.
8. **Shunt groups + rule-providers** - Each binding generates:
   - A `select` proxy-group: `[default_group, DIRECT, REJECT] + manual_groups + filtered_groups`
   - A `rule-providers` entry pointing to `{public_base_url}/api/public/configs/{id}/rules/{rule_id}.yaml?password=...`
   - A `RULE-SET,{provider_key},{binding_name}` rules line
9. **Final MATCH** - Appended last: `MATCH,{final_target}`
10. **Proxy filtering** - Only proxies referenced by any group are included. Internal `__` keys stripped.
11. **Merge** - Generated sections replace `proxies`, `proxy-groups`, `rule-providers`, `rules` in base YAML. Other base keys preserved.

Proxy group order in output: filtered_groups -> manual_groups -> shunt_groups.

## API Routes

All routes under `/api`. Admin routes require `Authorization: Bearer <token>`.

### Admin

| Method | Path                                                  | Purpose                     |
|--------|-------------------------------------------------------|-----------------------------|
| GET    | `/api/admin/health`                                   | Health + refresh loop status|
| GET    | `/api/admin/subscriptions`                            | List subscriptions          |
| POST   | `/api/admin/subscriptions`                            | Create subscription         |
| PUT    | `/api/admin/subscriptions/{id}`                       | Update subscription         |
| POST   | `/api/admin/subscriptions/{id}/refresh`               | Sync refresh                |
| POST   | `/api/admin/subscriptions/{id}/refresh-async`         | Async refresh               |
| DELETE | `/api/admin/subscriptions/{id}`                       | Delete subscription         |
| GET    | `/api/admin/rules`                                    | List rules                  |
| POST   | `/api/admin/rules`                                    | Create rule                 |
| PUT    | `/api/admin/rules/{id}`                               | Update rule                 |
| POST   | `/api/admin/rules/{id}/refresh`                       | Sync refresh                |
| POST   | `/api/admin/rules/{id}/refresh-async`                 | Async refresh               |
| DELETE | `/api/admin/rules/{id}`                               | Delete rule                 |
| GET    | `/api/admin/main-configs`                             | List configs                |
| POST   | `/api/admin/main-configs`                             | Create config               |
| PUT    | `/api/admin/main-configs/{id}`                        | Update config               |
| DELETE | `/api/admin/main-configs/{id}`                        | Delete config               |
| POST   | `/api/admin/main-configs/{id}/preview`                | Preview generated YAML      |
| POST   | `/api/admin/main-configs/filtered-groups/preview`     | Preview filtered group matches |
| POST   | `/api/admin/main-configs/preview-draft`               | Preview uncommitted builder changes |

### Public

| Method | Path                                                        | Purpose            |
|--------|-------------------------------------------------------------|--------------------|
| GET    | `/api/public/configs/{id}/artifact?password=...`            | Generated YAML     |
| GET    | `/api/public/configs/{id}/rules/{rule_id}.yaml?password=...`| Rule payload YAML  |

## Key Backend Schemas

```python
# MainConfigCreate (POST /api/admin/main-configs)
# MainConfigUpdate (PUT /api/admin/main-configs/{id}) — all fields optional
# MainConfigRead — response model, includes all fields below
MainConfig fields:
  name, password_plain, base_config_yaml, enabled, final_target_type, final_target_group_name
  filtered_groups: [{name, position, group_mode, test_url?, test_interval_sec?, rules: [{subscription_source_id, regex_pattern, regex_flags, position}]}]
  manual_groups: [{name, position, group_mode, test_url?, test_interval_sec?, members: [{member_type, member_ref, position}]}]
  dialer_override_rules: [{filtered_group_name, dialer_group_name}]
  shunt_bindings: [{position, binding_name, rule_source_id, default_group_name, no_resolve}]

# Draft preview (POST /api/admin/main-configs/preview-draft)
DraftPreviewRequest:
  base_config_yaml: str
  password_plain: str
  final_target_type: FinalTargetType
  final_target_group_name: str | None
  config_id: str | None
  filtered_groups: list[FilteredGroupPayload]  # same shape as MainConfig fields
  manual_groups: list[ManualGroupPayload]
  dialer_override_rules: list[DialerOverridePayload]
  shunt_bindings: list[ShuntBindingPayload]

# Preview response
PreviewWithDiagnosticsResponse:
  yaml: str
  diagnostics: {stale_subscription_ids, stale_rule_ids, warnings}

# Generator input (internal, not an API schema)
GenerationInput:
  config_id, base_config_yaml, password_plain, final_target_type, final_target_group_name
  filtered_groups, manual_groups, dialer_override_rules, shunt_bindings

# Type enums
GroupMode: "select" | "fallback" | "url-test"
MemberType: "filtered_group" | "manual_group"
FinalTargetType: "DIRECT" | "REJECT" | "group"
RuleBehavior: "classical" | "domain" | "ipcidr"
```

## Environment Variables (`backend/app/config.py`)

| Variable                  | Default                              | Notes                                |
|---------------------------|--------------------------------------|--------------------------------------|
| `ADMIN_TOKEN`             | `change-me`                          | Bearer token for admin APIs          |
| `DATABASE_URL`            | `sqlite+aiosqlite:///./db.sqlite3`   |                                      |
| `PUBLIC_BASE_URL`         | `http://localhost:5678`              | Used in generated rule-provider URLs |
| `API_PREFIX`              | `/api`                               |                                      |
| `CORS_ORIGINS`            | `["http://localhost:3000", ...]`     |                                      |
| `REFRESH_LOOP_TICK_SEC`   | `15`                                 | Background refresh check interval    |
| `REQUEST_TIMEOUT_SEC`     | `30.0`                               | HTTP fetch timeout                   |
| `MIN_REFRESH_INTERVAL_SEC`| `60`                                 | Clamp for auto-update interval       |
| `MAX_REFRESH_INTERVAL_SEC`| `86400`                              | Clamp for auto-update interval       |
| `DEFAULT_TEST_URL`        | `https://www.gstatic.com/generate_204`| Fallback for group test_url         |
| `DEFAULT_TEST_INTERVAL`   | `300`                                | Fallback for group test_interval     |

## Background Refresh

- In-process async loop ticks every `REFRESH_LOOP_TICK_SEC` seconds.
- Finds remote + enabled + auto_update sources where `next_refresh_at <= now()`.
- Deduplicates concurrent refreshes per source ID via inflight sets.
- Jitter: `interval * uniform(0.9, 1.1)`, minimum 1 second.
- On failure: existing cache preserved, error recorded, next refresh scheduled.

## Frontend Patterns

- Auth: token in `localStorage` key `sub_manager_admin_token`. Axios interceptor adds bearer header.
- Routes: `/login`, `/subscriptions`, `/rules`, `/configs` (guarded).
- Builder editor: `MainConfigEditorDrawer.tsx` - visual form with collapsible sections for all builder parts.
- Frontend dev proxy: Vite proxies `/api` to `http://localhost:5678`.
- Path alias: `@` -> `frontend/src/`.

## Known Gaps / Technical Notes

- `Dashboard.tsx` and `About.tsx` are legacy pages not reachable from current router.
- Several frontend deps are unused by active pages (`@rjsf/*`, xterm, zustand).
- No Alembic migrations in use; runtime uses `create_all()`.
- No Docker files in this repository.
- Plaintext credentials by design (admin_token, password_plain).
