from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import random
import re

from fastapi import HTTPException
from starlette.requests import Request


def get_public_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@dataclass
class ServiceError(Exception):
    message: str
    status_code: int = 400


@dataclass
class GenerationError(Exception):
    message: str
    status_code: int = 422


def utc_now() -> datetime:
    return datetime.now(UTC)


def with_jitter(interval_sec: int) -> int:
    return max(1, int(interval_sec * random.uniform(0.9, 1.1)))


def next_refresh_time(interval_sec: int) -> datetime:
    return utc_now() + timedelta(seconds=with_jitter(interval_sec))


def parse_subscription_userinfo(raw: str | None) -> dict[str, int] | None:
    if not raw:
        return None

    out: dict[str, int] = {}
    for part in raw.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        try:
            out[key] = int(value)
        except ValueError:
            continue
    return out or None


def slugify_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "source"


def dedupe_keep_order(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        out.append(value)
        seen.add(value)
    return out


def to_http_error(exc: ServiceError | GenerationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)
