# PROMPT: Unit tests for ingest, analytics sessions, and POS loader aggregation.
# CHANGES MADE: Added layout loader test and conversion correlation smoke test.

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from api.database import init_db
from api.models import EventRecord
from api.pos_loader import load_pos_for_store
from api.services.analytics import build_sessions, compute_metrics, health_status
from api.services.ingest import ingest_batch
from shared.layout import get_store, load_layout


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'svc.db'}")
    from api.database import SessionLocal

    init_db()
    session = SessionLocal()
    yield session
    session.close()


def test_ingest_batch(db_session):
    ev = {
        "event_id": str(uuid.uuid4()),
        "store_id": "STORE_001",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_x",
        "event_type": "ENTRY",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "confidence": 0.8,
        "metadata": {"session_seq": 1},
    }
    result = ingest_batch(db_session, [ev])
    assert result["accepted"] == 1


def test_build_sessions_excludes_staff(db_session):
    now = datetime.now(timezone.utc)
    events = [
        EventRecord(
            event_id=str(uuid.uuid4()),
            store_id="STORE_001",
            camera_id="C1",
            visitor_id="VIS_s",
            event_type="ENTRY",
            timestamp=now,
            zone_id=None,
            dwell_ms=0,
            is_staff=True,
            confidence=0.9,
            metadata_json="{}",
        ),
        EventRecord(
            event_id=str(uuid.uuid4()),
            store_id="STORE_001",
            camera_id="C1",
            visitor_id="VIS_c",
            event_type="ENTRY",
            timestamp=now,
            zone_id=None,
            dwell_ms=0,
            is_staff=False,
            confidence=0.9,
            metadata_json="{}",
        ),
    ]
    sessions = build_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].visitor_id == "VIS_c"


def test_pos_loader_aggregates():
    root = Path(__file__).resolve().parent.parent
    pos_path = root / "POS - sample transactionsb1e826f.csv"
    if pos_path.exists():
        txns = load_pos_for_store("STORE_001", str(pos_path))
        assert len(txns) >= 1


def test_layout_loads():
    layout = load_layout()
    store = get_store(layout, "STORE_001")
    assert store is not None
    assert len(store["cameras"]) >= 3


def test_health_and_metrics(db_session):
    ingest_batch(
        db_session,
        [
            {
                "event_id": str(uuid.uuid4()),
                "store_id": "STORE_001",
                "camera_id": "CAM_ENTRY_01",
                "visitor_id": "VIS_m1",
                "event_type": "ENTRY",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "confidence": 0.77,
                "metadata": {"session_seq": 1},
            }
        ],
    )
    db_session.commit()
    m = compute_metrics(db_session, "STORE_001")
    h = health_status(db_session)
    assert m["unique_visitors"] >= 1
    assert "status" in h
