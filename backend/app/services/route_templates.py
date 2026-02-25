from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RouteTemplate
from app.repositories import route_templates as route_template_repo
from app.schemas.reorder import ReorderRequest
from app.schemas.route_templates import (
    RouteTemplateBindingPayload,
    RouteTemplateCreate,
    RouteTemplateSlotPayload,
    RouteTemplateUpdate,
)
from app.services.common import ServiceError


def validate_template_shapes(
    slots: list[RouteTemplateSlotPayload],
    bindings: list[RouteTemplateBindingPayload],
) -> None:
    slot_names = [s.name for s in slots]
    dupes = {n for n in slot_names if slot_names.count(n) > 1}
    if dupes:
        raise ServiceError(f"duplicate slot names: {sorted(dupes)}", 422)

    binding_names = [b.binding_name for b in bindings]
    dupes = {n for n in binding_names if binding_names.count(n) > 1}
    if dupes:
        raise ServiceError(f"duplicate binding names: {sorted(dupes)}", 422)

    slot_name_set = set(slot_names)
    for binding in bindings:
        if binding.default_target not in slot_name_set | {"DIRECT", "REJECT"}:
            raise ServiceError(
                f"binding '{binding.binding_name}' default_target '{binding.default_target}' "
                f"is not a slot name or DIRECT/REJECT",
                422,
            )


async def validate_template_refs(
    db: AsyncSession,
    bindings: list[RouteTemplateBindingPayload],
) -> None:
    rule_ids = {b.rule_source_id for b in bindings}
    if not rule_ids:
        return
    found = await route_template_repo.check_rule_source_ids_exist(db, rule_ids)
    missing = rule_ids - found
    if missing:
        raise ServiceError(f"unknown rule_source_id: {sorted(missing)}", 422)


async def create_route_template(
    db: AsyncSession, payload: RouteTemplateCreate
) -> RouteTemplate:
    if await route_template_repo.check_name_exists(db, payload.name):
        raise ServiceError(f"route template name already exists: {payload.name}", 409)
    if payload.slots or payload.bindings:
        validate_template_shapes(payload.slots, payload.bindings)
        await validate_template_refs(db, payload.bindings)

    max_pos = await route_template_repo.get_max_position(db)

    template = RouteTemplate(
        name=payload.name,
        slots=payload.slots,
        bindings=payload.bindings,
        position=max_pos + 1,
    )
    return await route_template_repo.save(db, template)


async def update_route_template(
    db: AsyncSession,
    template: RouteTemplate,
    payload: RouteTemplateUpdate,
) -> RouteTemplate:
    if payload.name is not None and payload.name != template.name:
        if await route_template_repo.check_name_exists(db, payload.name, exclude_id=template.id):
            raise ServiceError(f"route template name already exists: {payload.name}", 409)
        template.name = payload.name

    slots = payload.slots if payload.slots is not None else template.slots
    bindings = payload.bindings if payload.bindings is not None else template.bindings

    if payload.slots is not None or payload.bindings is not None:
        validate_template_shapes(slots, bindings)
        await validate_template_refs(db, bindings)
        template.slots = slots
        template.bindings = bindings

    return await route_template_repo.save(db, template)


async def list_route_templates(db: AsyncSession) -> list[RouteTemplate]:
    return await route_template_repo.list_all_ordered(db)


async def get_route_template_or_404(
    db: AsyncSession, template_id: str
) -> RouteTemplate:
    template = await route_template_repo.get_by_id(db, template_id)
    if template is None:
        raise ServiceError("route template not found", 404)
    return template


async def delete_route_template(db: AsyncSession, template: RouteTemplate) -> None:
    if await route_template_repo.has_referencing_main_configs(db, template.id):
        raise ServiceError("route template is referenced by a main config", 409)
    await route_template_repo.delete(db, template)


async def reorder_route_templates(db: AsyncSession, payload: ReorderRequest) -> None:
    await route_template_repo.bulk_update_positions(
        db, [(item.id, item.position) for item in payload.items]
    )
