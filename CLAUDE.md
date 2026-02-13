# Sub Manager

Clash Meta proxy subscription / routing rule management and config generation tool.

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
      main_configs.py              # config CRUD + builder + preview + filtered-group-preview
    routers/public/
      configs.py                   # public artifact + rule-payload fetch (password protected)
    schemas/                       # pydantic request/response models
      subscriptions.py
      rules.py
      configs.py                   # BuilderPayload, PreviewWithDiagnosticsResponse, DraftPreviewRequest, etc.
    services/                      # business logic
      common.py                    # ServiceError, GenerationError, jitter, slugify, parsing
      subscriptions.py             # subscription CRUD + remote fetch + cache
      rules.py                     # rule CRUD + remote fetch + validation
      main_configs.py              # config CRUD + builder replace + validation
      generator.py                 # YAML assembly engine
      refresh_loop.py              # in-process async background refresh
    repositories/                  # exists but currently unused by services
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

The system manages three resource types that compose into a final Clash Meta YAML config.

### Subscription Sources (`subscription_source`)

Proxy node providers. Two modes:
- **remote**: Fetched from URL with `User-Agent: mihomo/1.18.3`, optional `Authorization` header. Caches `proxies` list from YAML. Parses `subscription-userinfo` header for traffic data.
- **manual**: User provides a single YAML proxy object directly.

Fields: `id`, `name` (unique), `mode`, `enabled`, `remote_url`, `remote_auth_header`, `use_proxy`, `auto_update`, `update_interval_sec`, `next_refresh_at`, `last_status` (never/ok/error), `cached_proxies_json`.

### Rule Sources (`rule_source`)

Traffic routing rule providers. Two modes (remote/manual). Each has a `behavior`: `classical`, `domain`, or `ipcidr`. Cached as `payload_lines` (list of strings). Only YAML format supported.

### Main Configs (`main_config`) + Builder Graph

A main config combines subscriptions + rules into a final output. Each config has:
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

The generation pipeline (single code path for both saved configs and draft previews):

1. **Build `BuilderPayload`** - From `MainConfig` JSON columns (saved) or from `DraftPreviewRequest` (draft).
2. **Load builder state** - `_load_builder_state()` converts `BuilderPayload` into internal `BuilderState`, fetching referenced `SubscriptionSource` and `RuleSource` rows from DB.
3. **Load subscriptions** - Derive subscription IDs from filtered group rules (first-seen order). Gather cached proxies. Skip disabled (with warning). Fail on missing cache (409).
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
| GET    | `/api/admin/main-configs/{id}/builder`                | Get builder state           |
| PUT    | `/api/admin/main-configs/{id}/builder`                | Replace builder (full swap) |
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
# Builder payload (PUT /api/admin/main-configs/{id}/builder)
# Also used as the response type for GET builder and as JSON columns on MainConfig
BuilderPayload:
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
  builder: BuilderPayload

# Preview response
PreviewWithDiagnosticsResponse:
  yaml: str
  diagnostics: {stale_subscription_ids, stale_rule_ids, warnings}

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
| `QUERY_PASSWORD_NAME`     | `password`                           | Query param name in generated URLs   |

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

- `use_proxy` field on subscriptions is stored but not applied in the HTTP fetch path.
- `repositories/` layer exists but is unused; services query SQLAlchemy directly.
- `Dashboard.tsx` and `About.tsx` are legacy pages not reachable from current router.
- Several frontend deps are unused by active pages (`@rjsf/*`, xterm, zustand).
- No Alembic migrations in use; runtime uses `create_all()`.
- No Docker files in this repository.
- Plaintext credentials by design (admin_token, password_plain).
- `QUERY_PASSWORD_NAME` setting can diverge from hardcoded `password` query param in public endpoints.
