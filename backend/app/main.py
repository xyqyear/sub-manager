from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import init_db
from app.routers.health import router as health_router
from app.routers.items import router as items_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


api_app = FastAPI(title=f"{settings.app_name} API")
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
api_app.include_router(health_router)
api_app.include_router(items_router)

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount(settings.api_prefix, api_app)


@app.get("/")
async def read_root() -> dict[str, str]:
    return {"message": f"{settings.app_name} backend is running"}
