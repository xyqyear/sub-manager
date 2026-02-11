from datetime import UTC, datetime

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def get_health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}
