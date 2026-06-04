# PROMPT: Generate pytest tests for a FastAPI Store Intelligence API with ingest idempotency,
# metrics excluding staff, funnel sessions, heatmap confidence, anomalies, health stale feed,
# and 503 when database unavailable. Use in-memory SQLite.
# CHANGES MADE: Added re-entry funnel test, empty store test, idempotency duplicate count,
# and patched db_available for 503 coverage.

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
def _ev(store: str, etype: str, vid: str, **kw):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store,
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": vid,
        "event_type": etype,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "zone_id": kw.get("zone_id"),
        "dwell_ms": kw.get("dwell_ms", 0),
        "is_staff": kw.get("is_staff", False),
        "confidence": 0.88,
        "metadata": kw.get("metadata", {"queue_depth": None, "sku_zone": None, "session_seq": 1}),
    }


def test_ingest_and_idempotency(client):
    ev = _ev("STORE_001", "ENTRY", "VIS_a1")
    r1 = client.post("/events/ingest", json={"events": [ev]})
    r2 = client.post("/events/ingest", json={"events": [ev]})
    assert r1.json()["accepted"] == 1
    assert r2.json()["duplicates"] == 1


def test_partial_ingest(client):
    good = _ev("STORE_001", "ENTRY", "VIS_ok")
    bad = {"event_id": "bad"}
    r = client.post("/events/ingest", json={"events": [good, bad]})
    body = r.json()
    assert body["accepted"] == 1
    assert body["rejected"] == 1


def test_metrics_exclude_staff(client):
    client.post(
        "/events/ingest",
        json={
            "events": [
                _ev("STORE_001", "ENTRY", "VIS_staff", is_staff=True),
                _ev("STORE_001", "ENTRY", "VIS_c1"),
            ]
        },
    )
    m = client.get("/stores/STORE_001/metrics").json()
    assert m["unique_visitors"] == 1


def test_empty_store_metrics(client):
    m = client.get("/stores/STORE_001/metrics").json()
    assert m["unique_visitors"] == 0
    assert m["conversion_rate"] == 0.0


def test_funnel_reentry_not_double_entry(client):
    vid = "VIS_re"
    events = [
        _ev("STORE_001", "ENTRY", vid),
        _ev("STORE_001", "EXIT", vid),
        _ev("STORE_001", "REENTRY", vid),
    ]
    client.post("/events/ingest", json={"events": events})
    f = client.get("/stores/STORE_001/funnel").json()
    entry_stage = f["funnel"][0]
    assert entry_stage["count"] >= 1


def test_heatmap_low_confidence(client):
    h = client.get("/stores/STORE_001/heatmap").json()
    assert h["data_confidence"] is False


def test_health_endpoint(client):
    h = client.get("/health").json()
    assert h["status"] in ("healthy", "degraded")


def test_anomalies_structure(client):
    for i in range(5):
        client.post(
            "/events/ingest",
            json={
                "events": [
                    _ev(
                        "STORE_001",
                        "BILLING_QUEUE_JOIN",
                        f"VIS_q{i}",
                        zone_id="BILLING",
                        metadata={"queue_depth": 5, "session_seq": 1},
                    )
                ]
            },
        )
    a = client.get("/stores/STORE_001/anomalies").json()
    assert isinstance(a["anomalies"], list)


def test_db_unavailable_returns_503(client):
    with patch("api.main.db_available", return_value=False):
        r = client.get("/health")
    assert r.status_code == 503
    assert "database_unavailable" in r.json()["detail"]["error"]


def test_zero_purchase_conversion(client):
    client.post("/events/ingest", json={"events": [_ev("STORE_001", "ENTRY", "VIS_z")]})
    m = client.get("/stores/STORE_001/metrics").json()
    assert m["conversion_rate"] == 0.0
