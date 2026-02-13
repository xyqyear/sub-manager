from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BeforeValidator


def _ensure_utc(v: object) -> object:
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=UTC)
    return v


UtcDatetime = Annotated[datetime, BeforeValidator(_ensure_utc)]
