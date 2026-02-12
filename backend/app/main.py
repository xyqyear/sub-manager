from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import init_db
from app.routers.admin.health import router as admin_health_router
from app.routers.admin.main_configs import router as admin_main_configs_router
from app.routers.admin.rules import router as admin_rules_router
from app.routers.admin.subscriptions import router as admin_subscriptions_router
from app.routers.public.configs import router as public_configs_router
from app.services.refresh_loop import refresh_loop_manager

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"
FRONTEND_STATIC_DIR = FRONTEND_DIST_DIR / "static"


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

if FRONTEND_ASSETS_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_ASSETS_DIR.resolve()),
        name="assets",
    )

if FRONTEND_STATIC_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=FRONTEND_STATIC_DIR.resolve()),
        name="static",
    )


def _resolve_frontend_file(path: str) -> Path | None:
    candidate = (FRONTEND_DIST_DIR / path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST_DIR.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def _frontend_index_or_404() -> Path:
    index_file = FRONTEND_DIST_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "Frontend build not found. Run `pnpm build` in `frontend/` "
                "to generate static files."
            ),
        )
    return index_file


@app.get("/", include_in_schema=False)
async def serve_spa_root() -> FileResponse:
    return FileResponse(_frontend_index_or_404())


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str) -> FileResponse:
    api_prefix = settings.api_prefix.strip("/")
    if full_path == api_prefix or full_path.startswith(f"{api_prefix}/"):
        raise HTTPException(status_code=404, detail="Not found")

    if full_path:
        existing_file = _resolve_frontend_file(full_path)
        if existing_file is not None:
            return FileResponse(existing_file)

    return FileResponse(_frontend_index_or_404())
