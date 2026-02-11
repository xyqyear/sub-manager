from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models import Item
from app.schemas import ItemCreate, ItemRead

router = APIRouter(prefix="/items", tags=["items"])
SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[ItemRead])
async def list_items(db: SessionDep) -> list[Item]:
    result = await db.execute(select(Item).order_by(Item.id.desc()))
    return list(result.scalars().all())


@router.post("", response_model=ItemRead, status_code=201)
async def create_item(payload: ItemCreate, db: SessionDep) -> Item:
    item = Item(name=payload.name, done=payload.done)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item
