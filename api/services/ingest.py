from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from api.models import EventRecord
from shared.schema import StoreEvent


def parse_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def ingest_batch(session: Session, events: list[dict[str, Any]]) -> dict[str, Any]:
    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []
    duplicates = 0

    for raw in events:
        try:
            event = StoreEvent.model_validate(raw)
        except ValidationError as exc:
            rejected.append(
                {
                    "event_id": raw.get("event_id"),
                    "error": [{"type": e["type"], "msg": e["msg"]} for e in exc.errors()],
                }
            )
            continue

        existing = session.get(EventRecord, event.event_id)
        if existing:
            duplicates += 1
            accepted.append(event.event_id)
            continue

        record = EventRecord(
            event_id=event.event_id,
            store_id=event.store_id,
            camera_id=event.camera_id,
            visitor_id=event.visitor_id,
            event_type=event.event_type.value,
            timestamp=parse_timestamp(event.timestamp),
            zone_id=event.zone_id,
            dwell_ms=event.dwell_ms,
            is_staff=event.is_staff,
            confidence=event.confidence,
            metadata_json=json.dumps(event.metadata.model_dump()),
        )
        session.add(record)
        accepted.append(event.event_id)

    session.flush()
    return {
        "accepted": len(accepted),
        "rejected": len(rejected),
        "duplicates": duplicates,
        "accepted_ids": accepted,
        "rejected_details": rejected,
    }
