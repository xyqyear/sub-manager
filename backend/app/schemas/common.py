from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BeforeValidator


def _ensure_utc(v: object) -> object:
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=UTC)
    return v


UtcDatetime = Annotated[datetime, BeforeValidator(_ensure_utc)]

# ── Domain Literal types shared across schemas, models, and services ──

SourceMode = Literal["remote", "manual"]
RuleBehavior = Literal["classical", "domain", "ipcidr"]
LastStatus = Literal["never", "ok", "error"]
FinalTargetType = Literal["DIRECT", "REJECT", "group"]
GroupMode = Literal["select", "fallback", "url-test"]
MemberType = Literal["filtered_group", "manual_group"]
