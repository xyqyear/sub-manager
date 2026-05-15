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

# docker
docker compose up               # starts on :5678
```

Set `ADMIN_TOKEN` in `backend/.env` (defaults to `change-me`). Use same token to log in on the frontend. For Docker, set `ADMIN_TOKEN` as an environment variable or in a `.env` file next to `compose.yaml`.

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

Remote subscription payloads can be Clash/mihomo YAML with a top-level `proxies` list, raw URI subscription lines, or base64-wrapped URI subscription lines.

Each source provides a list of proxy nodes (e.g., "Hong Kong 1", "US IEPL 2", etc.).

**Stage 2 — Rule Sources: traffic routing rules**

Users add rule sets that define which domains/IPs should be matched. A rule source can be:

- A remote URL (e.g., a community-maintained list of ad domains or China IP ranges)
- Manually entered rules

Each rule source has a behavior type: `classical` (full rule syntax), `domain` (domain lists), or `ipcidr` (IP ranges). The system caches rule payloads locally and serves them from its own URL in the generated config.

**Stage 3 — Main Configs: the composition layer**

This is where everything comes together. A main config has:

- A base YAML (ports, DNS, TUN settings, etc. — everything except proxies, groups, and rules)
- Three builder field groups (filtered groups, manual groups, dialer overrides) that visually compose proxy groups
- A reference to a route template with slot mappings that define traffic routing rules (see below)

### The Builder

The builder is the core of the product. It has three sections that work together to produce the `proxies`, `proxy-groups`, `rule-providers`, and `rules` sections of the final Clash Meta config. Route bindings are defined separately in route templates.

**Filtered Groups** — "Give me specific nodes from a subscription"

Each filtered group defines regex rules against one or more subscription sources. Example:

- Name: "HK", regex `香港|HK|Hong Kong` against subscription "Provider A" → produces a proxy group containing only matching HK nodes
- Mode: `select` (manual pick), `url-test` (auto-select fastest), or `fallback` (auto-failover)
- `copy_nodes`: when enabled, duplicates matched proxies with `[GroupName]` suffix so the same node can appear in multiple groups independently (useful for dialer-proxy chains)

Only nodes matched by at least one filtered group appear in the final config. Unmatched nodes are excluded entirely.

**Manual Groups** — "Combine groups for advanced routing"

Manual groups reference filtered groups or other manual groups as members. Use cases:

- A "Node Select" group containing "HK", "JP", "US" filtered groups plus an "Auto Select" url-test group
- A load-balancing or failover group across multiple regions

**Dialer Overrides** — "Route traffic through a proxy chain"

Assigns a `dialer-proxy` to all nodes in a filtered group, creating a relay chain. Example:

- All nodes in "My VPS" group get `dialer-proxy: "US Transit"` → traffic goes: client → US Transit node → VPS node → destination
- This hides the final destination from the transit provider and hides the transit from the destination

**Route Templates** — "Reusable routing rule definitions with named slots"

Route templates are standalone resources that define route bindings with named "slots" as placeholders for proxy groups. A template has:

- **Slots**: Named placeholders (e.g., "Node Select", "Streaming") that represent proxy group positions
- **Bindings**: Ordered list of route rules, each pairing a rule source with a binding name and a default target (a slot name, DIRECT, or REJECT)

Multiple main configs can reference the same route template. Each config provides **slot mappings** that map each slot name to an actual proxy group name from its filtered/manual groups.

Each route binding generates a `select`-type proxy group whose members are: `[default_group, DIRECT] + manual_groups + filtered_groups + [REJECT]`, allowing the user to override the default at runtime in Clash Meta.

The order of bindings determines rule matching priority in the generated config. A final implicit MATCH rule catches all remaining traffic, directed to DIRECT, REJECT, or a chosen group.

### Output

The system generates a complete Clash Meta YAML config accessible via a public URL (secured by unguessable UUID). Clash Meta clients subscribe to this URL. When subscriptions or rules refresh, the generated config automatically reflects the latest data.

Rule payloads referenced in the config's `rule-providers` section point back to this server's own URLs (not the original remote URLs), so the system acts as a caching proxy for rules.

## Tech Stack

| Layer    | Stack                                                  |
| -------- | ------------------------------------------------------ |
| Backend  | FastAPI + async SQLAlchemy + aiosqlite, Python >= 3.13 |
| Frontend | React 19 + Vite 7 + shadcn/ui + Tailwind CSS 4 + TypeScript 5.9 |
| Database | SQLite (single file `backend/db.sqlite3`)              |
| Auth     | Static bearer token (admin)                            |
| Deploy   | Docker (multi-stage build, single container)           |

## Repository Layout

```
Dockerfile                         # multi-stage: frontend build + backend venv + runtime
compose.yaml                       # single-service deployment
.dockerignore
backend/
  main.py                          # dev entrypoint (uvicorn, port 5678, reload)
  alembic.ini                      # Alembic configuration
  app/
    main.py                        # FastAPI app factory, lifespan, router mounting
    config.py                      # pydantic-settings (env-driven)
    auth.py                        # bearer token dependency
    yaml.py                        # ruamel.yaml wrapper (yaml_load, yaml_dump, YAMLError)
    models.py                      # SQLAlchemy ORM models
    db/database.py                 # async engine/session, init_db() with Alembic
    repositories/                  # data access layer (DB queries and mutations)
      subscriptions.py             # subscription CRUD + queries
      rules.py                     # rule CRUD + queries
      route_templates.py           # route template CRUD + queries
      main_configs.py              # main config CRUD + queries
    routers/admin/                 # admin CRUD APIs (bearer protected)
      health.py                    # GET /api/admin/health
      subscriptions.py             # subscription CRUD + refresh
      rules.py                     # rule CRUD + refresh
      route_templates.py           # route template CRUD
      main_configs.py              # config CRUD + preview + filtered-group-preview
    routers/public/
      configs.py                   # public artifact + rule-payload fetch
    schemas/                       # pydantic request/response models
      common.py                    # centralized Literal types + UtcDatetime
      subscriptions.py
      rules.py
      configs.py                   # MainConfigCreate/Update/Read, DraftPreviewRequest, etc.
      route_templates.py           # RouteTemplateCreate/Update/Read, slot/binding payloads
      reorder.py                   # ReorderRequest/ReorderItem for bulk position updates
    services/                      # business logic
      common.py                    # ServiceError, GenerationError, jitter, slugify, parsing
      subscriptions.py             # subscription CRUD + remote fetch + cache
      rules.py                     # rule CRUD + remote fetch + validation
      route_templates.py           # route template CRUD + validation
      main_configs.py              # config CRUD + validation
      generator.py                 # YAML assembly engine
      refresh_loop.py              # in-process async background refresh
  migrations/                      # Alembic migrations
    env.py
    versions/
      001_initial.py               # baseline schema
      002_route_templates.py       # route templates + data migration from route_bindings
      003_hoist_test_url.py        # move test_url/test_interval_sec from groups to main_config
      004_add_position_columns.py  # add position column to 4 top-level tables
  tests/
    conftest.py                    # test DB isolation (/tmp/sub_manager_test.sqlite3)
    test_admin_auth.py
    test_parsers.py
    test_generation_flow.py
    test_generator_steps.py
    test_migration.py

frontend/
  vite.config.ts                   # port 3000, /api proxy -> :5678, Tailwind + tsconfig-paths plugins
  components.json                  # shadcn/ui config (base-nova style, neutral base color)
  src/
    main.tsx                       # app bootstrap, theme provider, router, toast
    App.tsx                        # route guard + sidebar layout
    index.css                      # Tailwind CSS v4 imports, oklch theme variables, dark mode
    lib/
      utils.ts                     # cn() helper (clsx + tailwind-merge)
    utils/
      api.ts                       # axios instance + bearer interceptor + token storage
      download.ts                  # file download utility (Blob + click simulation)
      format.ts                    # formatBytes, TRAFFIC_COLORS
      time.ts                      # formatRelativeTime
    types/api.ts                   # TS interfaces matching backend schemas
    hooks/
      use-mobile.ts                # responsive breakpoint hook (768px)
    components/
      ui/                          # shadcn/ui components (@base-ui/react primitives)
        button, card, dialog, sheet, input, textarea, label, select, switch,
        alert, badge, skeleton, scroll-area, collapsible, popover, confirm-popover,
        tooltip, dropdown-menu, breadcrumb, separator, sidebar, sonner
      CardGrid.tsx                 # reusable card grid with optional drag-and-drop reorder
      app-sidebar.tsx              # navigation sidebar
      site-header.tsx              # page header with title
      theme-provider.tsx           # dark/light mode provider (next-themes)
      mode-toggle.tsx              # theme switcher button
      icons/
        index.tsx                  # custom SVG icons (InsertAbove, InsertBelow)
      dnd/                         # @dnd-kit drag-and-drop primitives
        DragHandle.tsx             # grab-handle icon with forwarded ref
        SortableItem.tsx           # useSortable wrapper, render-prop for drag handle
        SortableWrapper.tsx        # DndContext + SortableContext + sensors
        SortableFormList.tsx       # sortable list with add/insert/remove controls
    pages/
      Login.tsx
      Subscriptions.tsx            # subscription CRUD UI
      Rules.tsx                    # rule CRUD UI
      RouteTemplates.tsx           # route template CRUD UI
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

## Backend Architecture

The backend follows a three-layer pattern: **routers → services → repositories**.

- **Routers** handle HTTP concerns: request parsing, response serialization, error translation.
- **Services** contain business logic: validation, workflow orchestration, external HTTP fetches.
- **Repositories** encapsulate all database access: queries, mutations, position management.

Each of the four resource types (subscriptions, rules, route templates, main configs) has its own module in each layer. The generator is a standalone service that reads from repositories directly.

### Centralized Domain Types (`schemas/common.py`)

All domain Literal types are defined once and shared across schemas, models, and services:

```python
SourceMode = Literal["remote", "manual"]
RuleBehavior = Literal["classical", "domain", "ipcidr"]
LastStatus = Literal["never", "ok", "error"]
FinalTargetType = Literal["DIRECT", "REJECT", "group"]
GroupMode = Literal["select", "fallback", "url-test"]
MemberType = Literal["filtered_group", "manual_group"]

UtcDatetime = Annotated[datetime, BeforeValidator(_ensure_utc)]
```

ORM model columns use these types directly (e.g., `mode: Mapped[SourceMode]`), ensuring type consistency from database to API response.

### Repository Layer (`repositories/`)

Each repository module provides async functions for database operations. Common patterns across all four modules:

- `check_name_exists(db, name, exclude_id?)` — uniqueness check
- `get_max_position(db)` — next position value for ordering
- `save(db, entity)` — insert or update + commit + refresh
- `get_by_id(db, id)` — single row fetch
- `list_all_ordered(db)` — all rows ordered by position then created_at
- `delete(db, entity)` — delete + commit
- `bulk_update_positions(db, items)` — batch position update for reorder

Subscription and rule repositories additionally provide:
- `list_summary(db)` — optimized list query with computed count columns (e.g., `json_array_length` for cached proxy/rule counts)
- `get_due_ids(db)` — find sources due for background refresh
- `fetch_by_ids(db, ids)` — bulk fetch returning `dict[str, Entity]`

Route template repository adds `check_rule_source_ids_exist()` and `has_referencing_main_configs()`. Main config repository adds `check_subscription_ids_exist()`.

## Domain Model

The three resource types described in the Product Overview map to the following database tables and fields.

### Subscription Sources (`subscription_source`)

Corresponds to Stage 1 (proxy node providers). Two modes:

- **remote**: Fetched from URL with `User-Agent: mihomo.party/v1.8.9 (clash.meta)`, optional `Authorization` header. Caches proxies from Clash/mihomo YAML, raw URI subscription lines, or base64-wrapped URI subscription lines. Supported URI schemes are `ss`, `ssr`, `vmess`, `vless`, `trojan`, `hysteria`/`hy`, `hysteria2`/`hy2`, `tuic`, and `anytls`. Parses `subscription-userinfo` header for traffic data.
- **manual**: User provides a single YAML proxy object directly.

Fields: `id`, `name` (unique), `mode`, `enabled`, `remote_url`, `remote_auth_header`, `auto_update`, `update_interval_sec`, `next_refresh_at`, `last_refresh_at`, `last_status` (never/ok/error), `last_error`, `subscription_userinfo_raw`, `subscription_userinfo_json`, `cached_raw_yaml`, `cached_proxies_json`, `position`.

### Rule Sources (`rule_source`)

Corresponds to Stage 2 (traffic routing rules). Two modes (remote/manual). Each has a `behavior`: `classical`, `domain`, or `ipcidr`. Cached as `payload_lines` (list of strings). Only YAML format supported.

Fields: `id`, `name` (unique), `mode`, `behavior`, `enabled`, `remote_url`, `auto_update`, `update_interval_sec`, `next_refresh_at`, `last_refresh_at`, `last_status`, `last_error`, `cached_payload_lines_json`, `position`.

### Route Templates (`route_template`)

Standalone resource defining reusable route bindings with named slots. Multiple main configs can reference the same template.

Fields: `id`, `name` (unique), `slots` (PydanticListType of `RouteTemplateSlotPayload`), `bindings` (PydanticListType of `RouteTemplateBindingPayload`), `position`, `created_at`, `updated_at`.

Slots have `name` and `position`. Bindings have `position`, `binding_name`, `rule_source_id`, `default_target` (slot name, DIRECT, or REJECT), and `no_resolve`.

### Main Configs (`main_config`) + Builder Graph

Corresponds to Stage 3 (the composition layer). A main config combines subscriptions + rules into a final output. Each config has:

- `base_config_yaml`: base Clash settings (ports, DNS, TUN, etc.)
- `final_target_type`: DIRECT / REJECT / group (for the trailing MATCH rule)
- `final_target_group_name`: group name when `final_target_type` is "group"
- `test_url`: optional test URL for url-test/fallback groups (nullable, applied to all groups during generation)
- `test_interval_sec`: optional test interval in seconds (nullable, applied to all groups during generation)
- `route_template_id`: reference to a route template (nullable)
- `slot_mappings`: PydanticListType mapping each template slot name to an actual proxy group name
- A **builder graph** stored as 3 JSON columns directly on `main_config`, using a `PydanticListType` TypeDecorator that serializes/deserializes via Pydantic `TypeAdapter`:

| Column                  | Pydantic Type                 | Purpose                                                                        |
| ----------------------- | ----------------------------- | ------------------------------------------------------------------------------ |
| `filtered_groups`       | `list[FilteredGroupPayload]`  | Named proxy groups filtered by regex (each contains nested rules)              |
| `manual_groups`         | `list[ManualGroupPayload]`    | Named groups referencing filtered/manual groups (each contains nested members) |
| `dialer_override_rules` | `list[DialerOverridePayload]` | Assigns `dialer-proxy` to proxies in a filtered group                          |

All IDs are UUID strings (36 chars). All tables have `created_at`/`updated_at` timestamps and a `position` column for user-controlled ordering. Lists within JSON arrays are ordered by `position` field.

## Config Generation Engine (`services/generator.py`)

The generation pipeline uses a single `GenerationInput` model and `generate_config_yaml()` entry point for both saved configs and draft previews. Callers construct `GenerationInput` from either a `MainConfig` ORM object or a `DraftPreviewRequest` schema.

1. **Resolve route bindings** — `resolve_route_bindings()` fetches the route template (if any), maps slot names to group names via slot_mappings, and produces a list of `RouteBindingPayload` for the pipeline.
2. **Fetch subscriptions** — `_fetch_subscriptions()` derives subscription IDs from filtered group rules (first-seen order), fetches via `subscription_repo.fetch_by_ids()`.
3. **Fetch rule sources** — `_fetch_rule_sources()` fetches `RuleSource` rows via `rule_repo.fetch_by_ids()`.
4. **Load subscriptions** — `load_subscriptions()` gathers cached proxies. Skips disabled (with warning). Fails on missing cache (409). Enqueues stale refresh if overdue.
5. **Check rule staleness** — `check_rule_staleness()` enqueues stale rule refreshes.
6. **Name collision resolution** — `build_proxy_pool_with_collision_names()`: raw name → `raw@source_slug` → `raw@source_slug#N` if still colliding.
7. **Filtered groups** — `build_filtered_groups()` applies regex rules against source proxies. Match checks both final and raw names. Empty match = error (422). Supports `copy_nodes` mode that duplicates matched proxies with `[GroupName]` suffix. Group modes: `select`, `fallback`, `url-test`.
8. **Manual groups** — `build_manual_groups()` does recursive resolution. Members can be filtered groups or other manual groups. Cycle detection at runtime.
9. **Dialer overrides** — `apply_dialer_overrides()` targets a filtered group and assigns `dialer-proxy` to all proxies in that group. First-match-wins per proxy.
10. **Route groups + rule-providers** — `build_route_groups_and_rules()`: each binding generates:
    - A `select` proxy-group: `[default_group, DIRECT] + manual_groups + filtered_groups + [REJECT]`
    - A `rule-providers` entry pointing to `{request_base_url}/api/public/rules/{rule_id}.yaml`
    - A `RULE-SET,{provider_key},{binding_name}` rules line
11. **Final match group** — `build_final_match_group()` creates a `select` proxy-group named "Final" with the user's chosen default target (DIRECT/REJECT/group) as first member, followed by `[DIRECT, manual_groups, filtered_groups, REJECT]` (deduped). Appends `MATCH,Final` as the last rule.
12. **Proxy filtering** — `filter_and_clean_proxies()` keeps only proxies referenced by any group. Internal `__` keys stripped.
13. **Merge** — `merge_into_base_yaml()` replaces `proxies`, `proxy-groups`, `rule-providers`, `rules` in base YAML. Other base keys preserved.

The sync orchestrator `_generate_from_loaded_data()` runs steps 6–13 as pure functions via a `GenerationContext` dataclass. The async `generate_config_yaml()` entry point handles steps 1–5 (DB + refresh enqueueing) then delegates to the sync orchestrator.

Proxy group order in output: filtered_groups → manual_groups → route_groups.

## API Routes

All routes under `/api`. Admin routes require `Authorization: Bearer <token>`.

### Admin

| Method | Path                                              | Purpose                             |
| ------ | ------------------------------------------------- | ----------------------------------- |
| GET    | `/api/admin/health`                               | Health + refresh loop status        |
| GET    | `/api/admin/subscriptions`                        | List subscriptions (summary)        |
| GET    | `/api/admin/subscriptions/{id}`                   | Get subscription (full)             |
| POST   | `/api/admin/subscriptions`                        | Create subscription                 |
| PUT    | `/api/admin/subscriptions/{id}`                   | Update subscription                 |
| POST   | `/api/admin/subscriptions/{id}/refresh`           | Sync refresh                        |
| POST   | `/api/admin/subscriptions/{id}/refresh-async`     | Async refresh                       |
| DELETE | `/api/admin/subscriptions/{id}`                   | Delete subscription                 |
| PUT    | `/api/admin/subscriptions/reorder`                | Bulk reorder subscriptions          |
| GET    | `/api/admin/rules`                                | List rules (summary)                |
| GET    | `/api/admin/rules/{id}`                           | Get rule (full)                     |
| POST   | `/api/admin/rules`                                | Create rule                         |
| PUT    | `/api/admin/rules/{id}`                           | Update rule                         |
| POST   | `/api/admin/rules/{id}/refresh`                   | Sync refresh                        |
| POST   | `/api/admin/rules/{id}/refresh-async`             | Async refresh                       |
| DELETE | `/api/admin/rules/{id}`                           | Delete rule                         |
| PUT    | `/api/admin/rules/reorder`                        | Bulk reorder rules                  |
| GET    | `/api/admin/route-templates`                      | List route templates                |
| POST   | `/api/admin/route-templates`                      | Create route template               |
| PUT    | `/api/admin/route-templates/{id}`                 | Update route template               |
| DELETE | `/api/admin/route-templates/{id}`                 | Delete route template (protected)   |
| PUT    | `/api/admin/route-templates/reorder`              | Bulk reorder route templates        |
| GET    | `/api/admin/main-configs`                         | List configs                        |
| POST   | `/api/admin/main-configs`                         | Create config                       |
| PUT    | `/api/admin/main-configs/{id}`                    | Update config                       |
| DELETE | `/api/admin/main-configs/{id}`                    | Delete config                       |
| POST   | `/api/admin/main-configs/{id}/preview`            | Preview generated YAML              |
| POST   | `/api/admin/main-configs/filtered-groups/preview` | Preview filtered group matches      |
| POST   | `/api/admin/main-configs/preview-draft`           | Preview uncommitted builder changes |
| PUT    | `/api/admin/main-configs/reorder`                 | Bulk reorder main configs           |

### Public

| Method | Path                                | Purpose           |
| ------ | ----------------------------------- | ----------------- |
| GET    | `/api/public/configs/{id}/artifact` | Generated YAML    |
| GET    | `/api/public/rules/{rule_id}.yaml`  | Rule payload YAML |

## Key Backend Schemas

```python
# RouteTemplateCreate (POST /api/admin/route-templates)
# RouteTemplateUpdate (PUT /api/admin/route-templates/{id}) — all fields optional
# RouteTemplateRead — response model
RouteTemplate fields:
  name, slots: [{name, position}], bindings: [{position, binding_name, rule_source_id, default_target, no_resolve}]

# MainConfigCreate (POST /api/admin/main-configs)
# MainConfigUpdate (PUT /api/admin/main-configs/{id}) — all fields optional
# MainConfigRead — response model, includes all fields below
MainConfig fields:
  name, base_config_yaml, enabled, final_target_type, final_target_group_name
  test_url: str | None, test_interval_sec: int | None
  route_template_id: str | None
  slot_mappings: [{slot_name, group_name}]
  filtered_groups: [{name, position, group_mode, copy_nodes, rules: [{subscription_source_id, regex_pattern, regex_flags, position}]}]
  manual_groups: [{name, position, group_mode, members: [{member_type, member_ref, position}]}]
  dialer_override_rules: [{filtered_group_name, dialer_group_name}]

# Draft preview (POST /api/admin/main-configs/preview-draft)
DraftPreviewRequest:
  base_config_yaml: str
  final_target_type: FinalTargetType
  final_target_group_name: str | None
  config_id: str | None
  test_url: str | None
  test_interval_sec: int | None
  route_template_id: str | None
  slot_mappings: list[SlotMappingPayload]
  filtered_groups: list[FilteredGroupPayload]
  manual_groups: list[ManualGroupPayload]
  dialer_override_rules: list[DialerOverridePayload]

# Preview response
PreviewWithDiagnosticsResponse:
  yaml: str
  diagnostics: {stale_subscription_ids, stale_rule_ids, warnings}

# Generator input (internal, not an API schema)
GenerationInput:
  config_id, base_config_yaml, final_target_type, final_target_group_name, public_base_url
  test_url, test_interval_sec, route_template_id, slot_mappings, filtered_groups, manual_groups, dialer_override_rules

# RouteBindingPayload (internal, produced by resolve_route_bindings at generation time)
  position, binding_name, rule_source_id, default_group_name, no_resolve

# Type enums (defined in schemas/common.py)
SourceMode: "remote" | "manual"
GroupMode: "select" | "fallback" | "url-test"
MemberType: "filtered_group" | "manual_group"
FinalTargetType: "DIRECT" | "REJECT" | "group"
RuleBehavior: "classical" | "domain" | "ipcidr"
LastStatus: "never" | "ok" | "error"
```

## Environment Variables (`backend/app/config.py`)

| Variable                   | Default                                | Notes                             |
| -------------------------- | -------------------------------------- | --------------------------------- |
| `ADMIN_TOKEN`              | `change-me`                            | Bearer token for admin APIs       |
| `DATABASE_URL`             | `sqlite+aiosqlite:///./db.sqlite3`     |                                   |
| `API_PREFIX`               | `/api`                                 |                                   |
| `CORS_ORIGINS`             | `["http://localhost:3000", ...]`       |                                   |
| `SQL_ECHO`                 | `false`                                | SQLAlchemy query logging          |
| `REFRESH_LOOP_TICK_SEC`    | `15`                                   | Background refresh check interval |
| `REQUEST_TIMEOUT_SEC`      | `30.0`                                 | HTTP fetch timeout                |
| `MIN_REFRESH_INTERVAL_SEC` | `60`                                   | Clamp for auto-update interval    |
| `MAX_REFRESH_INTERVAL_SEC` | `86400`                                | Clamp for auto-update interval    |
| `DEFAULT_TEST_URL`         | `https://www.gstatic.com/generate_204` | Fallback for group test_url       |
| `DEFAULT_TEST_INTERVAL`    | `300`                                  | Fallback for group test_interval  |

## Background Refresh

- In-process async loop ticks every `REFRESH_LOOP_TICK_SEC` seconds.
- Finds remote + enabled + auto_update sources where `next_refresh_at <= now()` via repository `get_due_ids()`.
- Deduplicates concurrent refreshes per source ID via inflight sets.
- Jitter: `interval * uniform(0.9, 1.1)`, minimum 1 second.
- On failure: existing cache preserved, error recorded, next refresh scheduled.

## Frontend Patterns

- **UI framework**: shadcn/ui (base-nova style) built on `@base-ui/react` headless primitives, styled with Tailwind CSS v4. Components use `data-slot` attributes and CVA (class-variance-authority) for variants.
- **Styling**: Tailwind CSS v4 with CSS-first `@theme inline` configuration in `index.css`. Design tokens use oklch color space with CSS variables. Semantic colors: primary, secondary, muted, accent, destructive. `cn()` utility (clsx + tailwind-merge) for class merging.
- **Theming**: Dark/light mode via `next-themes` (`ThemeProvider` + `.dark` class). Geist Variable font family.
- **Layout**: Sidebar-based navigation (`app-sidebar.tsx`) with site header. Route guard in `App.tsx` redirects to `/login` if not authenticated.
- **Auth**: Token in `localStorage` key `sub_manager_admin_token`. Axios interceptor adds bearer header.
- **Routes**: `/login`, `/subscriptions`, `/rules`, `/routes`, `/configs` (guarded).
- **Forms**: `react-hook-form` with `Controller` for custom components + `@hookform/resolvers` with `zod` for schema validation.
- **Toast notifications**: `sonner` for all mutation feedback (success/error).
- **Code editor**: `@monaco-editor/react` + `monaco-yaml` for YAML editing in the builder.
- **Builder editor**: `MainConfigEditorDrawer.tsx` — visual form with collapsible sections for filtered groups (with live regex matching preview), manual groups, dialer overrides, and route template selection with slot mappings. Includes "Import from config" to copy all builder fields (except name/enabled) from an existing config.
- **Drag-and-drop**: `@dnd-kit/core` + `@dnd-kit/sortable` for reordering. Top-level card grids use `rectSortingStrategy`; form lists use `verticalListSortingStrategy` with isolated `DndContext` per nested list. Insert-above/below buttons on all sortable form lists.
- **Utilities**: `format.ts` (byte formatting, traffic colors), `time.ts` (relative time display), `download.ts` (file download via Blob).
- **Frontend dev proxy**: Vite proxies `/api` to `http://localhost:5678`.
- **Path alias**: `@` → `frontend/src/`.

## Known Gaps / Technical Notes

- Alembic manages schema migrations. On first run: `create_all()` + stamp head. On existing DBs without Alembic: stamps baseline + upgrades. On existing DBs with Alembic: runs pending upgrades.
- Migration testing convention: each new migration should have a corresponding test in `test_migration.py` that creates a temp DB at the prior revision, runs the migration, and verifies the result.
- Plaintext admin_token by design.
