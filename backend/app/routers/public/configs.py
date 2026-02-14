from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models import MainConfig, RuleSource
from app.services.common import GenerationError
from app.services.generator import GenerationInput, generate_config_yaml, render_rule_source_yaml

router = APIRouter(prefix="/public/configs", tags=["public-configs"])


def _check_password(config: MainConfig, password: str) -> None:
    if config.password_plain != password:
        raise HTTPException(status_code=401, detail="Invalid config password")


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
    password: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    config = await _get_config_or_404(db, config_id)
    _check_password(config, password)

    try:
        result = await generate_config_yaml(
            db,
            GenerationInput.from_main_config(config),
        )
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return PlainTextResponse(result.yaml, media_type="application/yaml")


@router.get("/{config_id}/rules/{rule_source_id}.yaml", response_class=PlainTextResponse)
async def get_rule_payload(
    config_id: str,
    rule_source_id: str,
    password: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    config = await _get_config_or_404(db, config_id)
    _check_password(config, password)

    if not any(b.rule_source_id == rule_source_id for b in config.route_bindings):
        raise HTTPException(status_code=404, detail="Rule source is not linked to config")

    rule_source = await db.get(RuleSource, rule_source_id)
    if rule_source is None:
        raise HTTPException(status_code=404, detail="Rule source not found")

    try:
        content = await render_rule_source_yaml(rule_source)
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return PlainTextResponse(content, media_type="application/yaml")
