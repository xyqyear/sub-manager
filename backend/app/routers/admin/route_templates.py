from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_token
from app.db.database import get_db
from app.schemas.reorder import ReorderRequest
from app.schemas.route_templates import (
    RouteTemplateCreate,
    RouteTemplateRead,
    RouteTemplateUpdate,
)
from app.services.common import ServiceError, to_http_error
from app.services.route_templates import (
    create_route_template,
    delete_route_template,
    get_route_template_or_404,
    list_route_templates,
    reorder_route_templates,
    update_route_template,
)

router = APIRouter(
    prefix="/admin/route-templates",
    tags=["admin-route-templates"],
    dependencies=[Depends(require_admin_token)],
)


@router.get("", response_model=list[RouteTemplateRead])
async def get_route_templates(db: AsyncSession = Depends(get_db)) -> list[RouteTemplateRead]:
    rows = await list_route_templates(db)
    return [RouteTemplateRead.model_validate(row) for row in rows]


@router.put("/reorder")
async def reorder_route_templates_endpoint(
    payload: ReorderRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await reorder_route_templates(db, payload)
    return {"status": "ok"}


@router.post("", response_model=RouteTemplateRead)
async def create_route_template_endpoint(
    payload: RouteTemplateCreate,
    db: AsyncSession = Depends(get_db),
) -> RouteTemplateRead:
    try:
        row = await create_route_template(db, payload)
        return RouteTemplateRead.model_validate(row)
    except ServiceError as exc:
        raise to_http_error(exc)


@router.put("/{template_id}", response_model=RouteTemplateRead)
async def update_route_template_endpoint(
    template_id: str,
    payload: RouteTemplateUpdate,
    db: AsyncSession = Depends(get_db),
) -> RouteTemplateRead:
    try:
        row = await get_route_template_or_404(db, template_id)
        row = await update_route_template(db, row, payload)
        return RouteTemplateRead.model_validate(row)
    except ServiceError as exc:
        raise to_http_error(exc)


@router.delete("/{template_id}")
async def delete_route_template_endpoint(
    template_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    try:
        row = await get_route_template_or_404(db, template_id)
        await delete_route_template(db, row)
        return {"status": "ok"}
    except ServiceError as exc:
        raise to_http_error(exc)
