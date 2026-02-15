from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_token
from app.db.database import get_db
from app.schemas.configs import (
    DraftPreviewRequest,
    FilteredGroupPreviewRequest,
    FilteredGroupPreviewResponse,
    GenerationDiagnostics,
    MainConfigCreate,
    MainConfigRead,
    MainConfigUpdate,
    PreviewWithDiagnosticsResponse,
)
from app.services.common import GenerationError, ServiceError, get_public_base_url, to_http_error
from app.services.generator import GenerationInput, generate_config_yaml
from app.services.main_configs import (
    _collect_group_names,
    create_main_config,
    delete_main_config,
    get_main_config_or_404,
    list_main_configs,
    preview_filtered_group_matches,
    update_main_config,
    validate_base_yaml,
    validate_builder_refs,
    validate_builder_shapes,
    validate_slot_mappings,
)

router = APIRouter(
    prefix="/admin/main-configs",
    tags=["admin-main-configs"],
    dependencies=[Depends(require_admin_token)],
)

@router.get("", response_model=list[MainConfigRead])
async def get_main_configs(db: AsyncSession = Depends(get_db)) -> list[MainConfigRead]:
    rows = await list_main_configs(db)
    return [MainConfigRead.model_validate(row) for row in rows]


@router.post("", response_model=MainConfigRead)
async def create_main_config_endpoint(
    payload: MainConfigCreate,
    db: AsyncSession = Depends(get_db),
) -> MainConfigRead:
    try:
        row = await create_main_config(db, payload)
        return MainConfigRead.model_validate(row)
    except ServiceError as exc:
        raise to_http_error(exc)


@router.post(
    "/filtered-groups/preview",
    response_model=FilteredGroupPreviewResponse,
)
async def preview_filtered_groups_endpoint(
    payload: FilteredGroupPreviewRequest,
    db: AsyncSession = Depends(get_db),
) -> FilteredGroupPreviewResponse:
    try:
        return await preview_filtered_group_matches(db, payload)
    except ServiceError as exc:
        raise to_http_error(exc)


@router.post("/preview-draft", response_model=PreviewWithDiagnosticsResponse)
async def preview_draft_endpoint(
    payload: DraftPreviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PreviewWithDiagnosticsResponse:
    try:
        validate_base_yaml(payload.base_config_yaml)
        validate_builder_shapes(
            payload.filtered_groups, payload.manual_groups,
            payload.dialer_override_rules,
        )
        await validate_builder_refs(db, payload.filtered_groups)
        group_name_set = _collect_group_names(payload.filtered_groups, payload.manual_groups)
        await validate_slot_mappings(db, payload.route_template_id, payload.slot_mappings, group_name_set)
        result = await generate_config_yaml(
            db,
            GenerationInput.from_draft(payload, public_base_url=get_public_base_url(request)),
        )
        return PreviewWithDiagnosticsResponse(
            yaml=result.yaml,
            diagnostics=GenerationDiagnostics(
                stale_subscription_ids=result.diagnostics.stale_subscription_ids,
                stale_rule_ids=result.diagnostics.stale_rule_ids,
                warnings=result.diagnostics.warnings,
            ),
        )
    except ServiceError as exc:
        raise to_http_error(exc)
    except GenerationError as exc:
        raise to_http_error(exc)


@router.put("/{config_id}", response_model=MainConfigRead)
async def update_main_config_endpoint(
    config_id: str,
    payload: MainConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> MainConfigRead:
    try:
        row = await get_main_config_or_404(db, config_id)
        row = await update_main_config(db, row, payload)
        return MainConfigRead.model_validate(row)
    except ServiceError as exc:
        raise to_http_error(exc)


@router.delete("/{config_id}")
async def delete_main_config_endpoint(
    config_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    try:
        row = await get_main_config_or_404(db, config_id)
        await delete_main_config(db, row)
        return {"status": "ok"}
    except ServiceError as exc:
        raise to_http_error(exc)


@router.post("/{config_id}/preview", response_model=PreviewWithDiagnosticsResponse)
async def preview_config_endpoint(
    config_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PreviewWithDiagnosticsResponse:
    try:
        config = await get_main_config_or_404(db, config_id)
        result = await generate_config_yaml(
            db,
            GenerationInput.from_main_config(config, public_base_url=get_public_base_url(request)),
        )
        return PreviewWithDiagnosticsResponse(
            yaml=result.yaml,
            diagnostics=GenerationDiagnostics(
                stale_subscription_ids=result.diagnostics.stale_subscription_ids,
                stale_rule_ids=result.diagnostics.stale_rule_ids,
                warnings=result.diagnostics.warnings,
            ),
        )
    except ServiceError as exc:
        raise to_http_error(exc)
    except GenerationError as exc:
        raise to_http_error(exc)
