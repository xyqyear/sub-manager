from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import init_db
from app.routers.admin.health import router as admin_health_router
from app.routers.admin.main_configs import router as admin_main_configs_router
from app.routers.admin.rules import router as admin_rules_router
from app.routers.admin.subscriptions import router as admin_subscriptions_router
from app.routers.public.configs import router as public_configs_router
from app.services.refresh_loop import refresh_loop_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await refresh_loop_manager.start()
    try:
        yield
    finally:
        await refresh_loop_manager.stop()


api_app = FastAPI(title=f"{settings.app_name} API")
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_app.include_router(admin_health_router)
api_app.include_router(admin_subscriptions_router)
api_app.include_router(admin_rules_router)
api_app.include_router(admin_main_configs_router)
api_app.include_router(public_configs_router)

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount(settings.api_prefix, api_app)


@app.get("/")
async def read_root() -> dict[str, str]:
    return {"message": f"{settings.app_name} backend is running"}
