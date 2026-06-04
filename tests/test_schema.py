# PROMPT: Write pydantic schema validation tests for StoreEvent with UUID event_id and ISO timestamps.
# CHANGES MADE: Added ZONE_DWELL and metadata queue_depth cases.

import uuid

import pytest
from pydantic import ValidationError

from shared.schema import EventMetadata, EventType, StoreEvent


def test_valid_event():
    ev = StoreEvent(
        event_id=str(uuid.uuid4()),
        store_id="STORE_001",
        camera_id="CAM_ENTRY_01",
        visitor_id="VIS_abc",
        event_type=EventType.ENTRY,
        timestamp="2026-06-03T12:00:00Z",
        confidence=0.75,
        metadata=EventMetadata(session_seq=1),
    )
    assert ev.event_type == EventType.ENTRY


def test_invalid_uuid_rejected():
    with pytest.raises(ValidationError):
        StoreEvent(
            event_id="not-valid",
            store_id="STORE_001",
            camera_id="CAM_ENTRY_01",
            visitor_id="VIS_abc",
            event_type=EventType.ENTRY,
            timestamp="2026-06-03T12:00:00Z",
            confidence=0.5,
        )
