from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.common import UtcDatetime


class RouteTemplateSlotPayload(BaseModel):
    name: str
    position: int


class RouteTemplateBindingPayload(BaseModel):
    position: int
    binding_name: str
    rule_source_id: str
    default_target: str  # slot name, "DIRECT", or "REJECT"
    no_resolve: bool = False


class RouteTemplateCreate(BaseModel):
    name: str
    slots: list[RouteTemplateSlotPayload] = []
    bindings: list[RouteTemplateBindingPayload] = []


class RouteTemplateUpdate(BaseModel):
    name: str | None = None
    slots: list[RouteTemplateSlotPayload] | None = None
    bindings: list[RouteTemplateBindingPayload] | None = None


class RouteTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slots: list[RouteTemplateSlotPayload]
    bindings: list[RouteTemplateBindingPayload]
    created_at: UtcDatetime
    updated_at: UtcDatetime
