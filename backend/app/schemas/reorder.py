from __future__ import annotations

from pydantic import BaseModel


class ReorderItem(BaseModel):
    id: str
    position: int


class ReorderRequest(BaseModel):
    items: list[ReorderItem]
