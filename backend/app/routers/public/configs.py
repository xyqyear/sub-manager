from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models import MainConfig, RuleSource
from app.services.common import GenerationError, get_public_base_url
from app.services.generator import GenerationInput, generate_config_yaml, render_rule_source_yaml

router = APIRouter(prefix="/public/configs", tags=["public-configs"])
rules_router = APIRouter(prefix="/public/rules", tags=["public-rules"])


async def _get_config_or_404(db: AsyncSession, config_id: str) -> MainConfig:
    config = await db.get(MainConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")
    if not config.enabled:
        raise HTTPException(status_code=404, detail="Config disabled")
    return config


@router.get("/{config_id}/artifact", response_class=PlainTextResponse)
async def get_artifact(
    config_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    config = await _get_config_or_404(db, config_id)

    try:
        result = await generate_config_yaml(
            db,
            GenerationInput.from_main_config(config, public_base_url=get_public_base_url(request)),
        )
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return PlainTextResponse(result.yaml, media_type="application/yaml")


@rules_router.get("/{rule_source_id}.yaml", response_class=PlainTextResponse)
async def get_rule_payload(
    rule_source_id: str,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    rule_source = await db.get(RuleSource, rule_source_id)
    if rule_source is None:
        raise HTTPException(status_code=404, detail="Rule source not found")

    try:
        content = await render_rule_source_yaml(rule_source)
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return PlainTextResponse(content, media_type="application/yaml")
