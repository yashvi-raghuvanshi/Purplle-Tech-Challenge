"""Canonical event schema for Store Intelligence pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"


class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: int = 0


class StoreEvent(BaseModel):
    event_id: str
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: EventType
    timestamp: str
    zone_id: Optional[str] = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    @field_validator("event_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        UUID(v, version=4)
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


def event_to_dict(event: StoreEvent) -> dict[str, Any]:
    d = event.model_dump()
    d["event_type"] = event.event_type.value
    return d
