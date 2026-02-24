from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MainConfig, RouteTemplate, RuleSource
from app.schemas.reorder import ReorderRequest
from app.schemas.route_templates import (
    RouteTemplateBindingPayload,
    RouteTemplateCreate,
    RouteTemplateSlotPayload,
    RouteTemplateUpdate,
)
from app.services.common import ServiceError


async def _assert_unique_template_name(db: AsyncSession, name: str, exclude_id: str | None = None) -> None:
    query = select(RouteTemplate).where(RouteTemplate.name == name)
    if exclude_id:
        query = query.where(RouteTemplate.id != exclude_id)
    found = await db.scalars(query)
    if found.first():
        raise ServiceError(f"route template name already exists: {name}", 409)


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
    result = await db.scalars(select(RuleSource.id).where(RuleSource.id.in_(rule_ids)))
    found = set(result.all())
    missing = rule_ids - found
    if missing:
        raise ServiceError(f"unknown rule_source_id: {sorted(missing)}", 422)


async def create_route_template(db: AsyncSession, payload: RouteTemplateCreate) -> RouteTemplate:
    await _assert_unique_template_name(db, payload.name)
    if payload.slots or payload.bindings:
        validate_template_shapes(payload.slots, payload.bindings)
        await validate_template_refs(db, payload.bindings)

    max_pos = (await db.execute(select(func.coalesce(func.max(RouteTemplate.position), -1)))).scalar()

    template = RouteTemplate(
        name=payload.name,
        slots=payload.slots,
        bindings=payload.bindings,
        position=max_pos + 1,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def update_route_template(
    db: AsyncSession, template: RouteTemplate, payload: RouteTemplateUpdate,
) -> RouteTemplate:
    if payload.name is not None and payload.name != template.name:
        await _assert_unique_template_name(db, payload.name, exclude_id=template.id)
        template.name = payload.name

    slots = payload.slots if payload.slots is not None else template.slots
    bindings = payload.bindings if payload.bindings is not None else template.bindings

    if payload.slots is not None or payload.bindings is not None:
        validate_template_shapes(slots, bindings)
        await validate_template_refs(db, bindings)
        template.slots = slots
        template.bindings = bindings

    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def list_route_templates(db: AsyncSession) -> list[RouteTemplate]:
    result = await db.scalars(select(RouteTemplate).order_by(RouteTemplate.position.asc(), RouteTemplate.created_at.desc()))
    return list(result.all())


async def get_route_template_or_404(db: AsyncSession, template_id: str) -> RouteTemplate:
    template = await db.get(RouteTemplate, template_id)
    if template is None:
        raise ServiceError("route template not found", 404)
    return template


async def delete_route_template(db: AsyncSession, template: RouteTemplate) -> None:
    result = await db.scalars(
        select(MainConfig.id).where(MainConfig.route_template_id == template.id).limit(1)
    )
    if result.first():
        raise ServiceError("route template is referenced by a main config", 409)
    await db.delete(template)
    await db.commit()


async def reorder_route_templates(db: AsyncSession, payload: ReorderRequest) -> None:
    for item in payload.items:
        await db.execute(
            update(RouteTemplate)
            .where(RouteTemplate.id == item.id)
            .values(position=item.position)
        )
    await db.commit()
