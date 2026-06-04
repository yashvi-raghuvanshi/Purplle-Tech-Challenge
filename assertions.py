"""
Example assertions for Store Intelligence API (challenge sample suite).
Run: pytest assertions.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

API_URL = "http://localhost:8000"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=API_URL, timeout=30.0) as c:
        yield c


def _event(store_id: str, etype: str, visitor: str, offset: int = 0, **kwargs):
    base = datetime.now(timezone.utc)
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": visitor,
        "event_type": etype,
        "timestamp": (base + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "zone_id": kwargs.get("zone_id"),
        "dwell_ms": kwargs.get("dwell_ms", 0),
        "is_staff": kwargs.get("is_staff", False),
        "confidence": kwargs.get("confidence", 0.9),
        "metadata": kwargs.get(
            "metadata", {"queue_depth": None, "sku_zone": None, "session_seq": 1}
        ),
    }


def test_01_health_returns_status(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "stores" in body


def test_02_ingest_accepts_valid_batch(client):
    events = [_event("STORE_001", "ENTRY", f"VIS_t{i}") for i in range(3)]
    r = client.post("/events/ingest", json={"events": events})
    assert r.status_code == 200
    assert r.json()["accepted"] == 3


def test_03_ingest_idempotent_by_event_id(client):
    ev = _event("STORE_001", "ENTRY", "VIS_idem")
    r1 = client.post("/events/ingest", json={"events": [ev]})
    r2 = client.post("/events/ingest", json={"events": [ev]})
    assert r1.json()["accepted"] == 1
    assert r2.json()["duplicates"] >= 1


def test_04_ingest_partial_success_on_malformed(client):
    good = _event("STORE_001", "ENTRY", "VIS_good")
    bad = {"event_id": "not-uuid", "store_id": "STORE_001"}
    r = client.post("/events/ingest", json={"events": [good, bad]})
    assert r.status_code == 200
    assert r.json()["rejected"] == 1
    assert r.json()["accepted"] == 1


def test_05_metrics_exclude_staff(client):
    staff = _event("STORE_001", "ENTRY", "VIS_staff", is_staff=True)
    cust = _event("STORE_001", "ENTRY", "VIS_cust_unique")
    client.post("/events/ingest", json={"events": [staff, cust]})
    m = client.get("/stores/STORE_001/metrics").json()
    assert m["unique_visitors"] >= 0
    assert m["customer_events"] >= 1


def test_06_metrics_zero_traffic_no_crash(client):
    r = client.get("/stores/STORE_999/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["unique_visitors"] == 0
    assert body["conversion_rate"] == 0.0


def test_07_funnel_session_based(client):
    vid = f"VIS_fun_{uuid.uuid4().hex[:4]}"
    events = [
        _event("STORE_001", "ENTRY", vid, 0),
        _event("STORE_001", "ZONE_ENTER", vid, 10, zone_id="SKINCARE"),
        _event("STORE_001", "BILLING_QUEUE_JOIN", vid, 20, zone_id="BILLING", metadata={"queue_depth": 1, "session_seq": 3}),
    ]
    client.post("/events/ingest", json={"events": events})
    f = client.get("/stores/STORE_001/funnel").json()
    assert "funnel" in f
    assert len(f["funnel"]) == 4


def test_08_heatmap_data_confidence_flag(client):
    h = client.get("/stores/STORE_001/heatmap").json()
    assert "data_confidence" in h
    assert "zones" in h


def test_09_anomalies_include_severity_and_action(client):
    a = client.get("/stores/STORE_001/anomalies").json()
    assert "anomalies" in a
    for item in a["anomalies"]:
        assert item["severity"] in ("INFO", "WARN", "CRITICAL")
        assert "suggested_action" in item


def test_10_batch_limit_enforced(client):
    events = [_event("STORE_001", "ENTRY", f"VIS_b{i}") for i in range(501)]
    r = client.post("/events/ingest", json={"events": events})
    assert r.status_code == 422 or r.status_code == 400
