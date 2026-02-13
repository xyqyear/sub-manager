from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_token
from app.db.database import get_db
from app.schemas.configs import (
    BuilderPayload,
    BuilderRead,
    DraftPreviewRequest,
    FilteredGroupPreviewRequest,
    FilteredGroupPreviewResponse,
    GenerationDiagnostics,
    MainConfigCreate,
    MainConfigRead,
    MainConfigUpdate,
    PreviewWithDiagnosticsResponse,
)
from app.services.common import GenerationError, ServiceError
from app.services.generator import generate_config_yaml, generate_config_yaml_from_draft
from app.services.main_configs import (
    create_main_config,
    delete_main_config,
    get_builder,
    get_main_config_or_404,
    list_main_configs,
    preview_filtered_group_matches,
    replace_builder,
    update_main_config,
    validate_base_yaml,
    validate_builder_refs,
    validate_builder_shapes,
)
from app.services.refresh_loop import refresh_loop_manager

router = APIRouter(
    prefix="/admin/main-configs",
    tags=["admin-main-configs"],
    dependencies=[Depends(require_admin_token)],
)


def _to_http_error(exc: ServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _to_gen_http_error(exc: GenerationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


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
        raise _to_http_error(exc)


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
        raise _to_http_error(exc)


@router.post("/preview-draft", response_model=PreviewWithDiagnosticsResponse)
async def preview_draft_endpoint(
    payload: DraftPreviewRequest,
    db: AsyncSession = Depends(get_db),
) -> PreviewWithDiagnosticsResponse:
    try:
        validate_base_yaml(payload.base_config_yaml)
        validate_builder_shapes(payload.builder)
        await validate_builder_refs(db, payload.builder)
        result = await generate_config_yaml_from_draft(
            db,
            payload,
            enqueue_subscription_refresh=refresh_loop_manager.enqueue_subscription_refresh,
            enqueue_rule_refresh=refresh_loop_manager.enqueue_rule_refresh,
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
        raise _to_http_error(exc)
    except GenerationError as exc:
        raise _to_gen_http_error(exc)


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
        raise _to_http_error(exc)


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
        raise _to_http_error(exc)


@router.get("/{config_id}/builder", response_model=BuilderRead)
async def get_builder_endpoint(
    config_id: str,
    db: AsyncSession = Depends(get_db),
) -> BuilderRead:
    try:
        _ = await get_main_config_or_404(db, config_id)
        return await get_builder(db, config_id)
    except ServiceError as exc:
        raise _to_http_error(exc)


@router.put("/{config_id}/builder", response_model=BuilderRead)
async def put_builder_endpoint(
    config_id: str,
    payload: BuilderPayload,
    db: AsyncSession = Depends(get_db),
) -> BuilderRead:
    try:
        _ = await get_main_config_or_404(db, config_id)
        return await replace_builder(db, config_id, payload)
    except ServiceError as exc:
        raise _to_http_error(exc)


@router.post("/{config_id}/preview", response_model=PreviewWithDiagnosticsResponse)
async def preview_config_endpoint(
    config_id: str,
    db: AsyncSession = Depends(get_db),
) -> PreviewWithDiagnosticsResponse:
    try:
        config = await get_main_config_or_404(db, config_id)
        result = await generate_config_yaml(
            db,
            config,
            enqueue_subscription_refresh=refresh_loop_manager.enqueue_subscription_refresh,
            enqueue_rule_refresh=refresh_loop_manager.enqueue_rule_refresh,
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
        raise _to_http_error(exc)
    except GenerationError as exc:
        raise _to_gen_http_error(exc)
