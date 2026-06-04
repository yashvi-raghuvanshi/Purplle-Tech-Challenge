#!/usr/bin/env python3
"""Seed canonical demo events for API testing when clips are sparse."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
API_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def build_events(store_id: str, base: datetime) -> list[dict]:
    visitors = [f"VIS_demo{i}" for i in range(1, 6)]
    events = []
    seq = 0

    def add(vid, etype, offset_s, zone=None, dwell=0, staff=False, meta=None):
        nonlocal seq
        seq += 1
        ts = (base + timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        events.append(
            {
                "event_id": str(uuid.uuid4()),
                "store_id": store_id,
                "camera_id": "CAM_ENTRY_01",
                "visitor_id": vid,
                "event_type": etype,
                "timestamp": ts,
                "zone_id": zone,
                "dwell_ms": dwell,
                "is_staff": staff,
                "confidence": 0.82,
                "metadata": meta or {"session_seq": seq, "sku_zone": None, "queue_depth": None},
            }
        )

    for i, vid in enumerate(visitors):
        t0 = i * 40
        add(vid, "ENTRY", t0)
        add(vid, "ZONE_ENTER", t0 + 15, "SKINCARE", meta={"sku_zone": "MOISTURISER", "session_seq": 2})
        add(vid, "ZONE_DWELL", t0 + 50, "SKINCARE", dwell=30000, meta={"sku_zone": "MOISTURISER", "session_seq": 3})
        add(vid, "BILLING_QUEUE_JOIN", t0 + 70, "BILLING", meta={"queue_depth": 2, "sku_zone": "CHECKOUT", "session_seq": 4})
        if i == 2:
            add(vid, "BILLING_QUEUE_ABANDON", t0 + 95, "BILLING", meta={"session_seq": 5})
        add(vid, "EXIT", t0 + 110)

    add("VIS_staff1", "ENTRY", 5, staff=True)
    add("VIS_staff1", "ZONE_ENTER", 20, "SKINCARE", staff=True)
    add("VIS_reentry", "ENTRY", 200)
    add("VIS_reentry", "EXIT", 260)
    add("VIS_reentry", "REENTRY", 320)
    return events


def main() -> None:
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    all_events = []
    for sid in ("STORE_001", "STORE_002"):
        all_events.extend(build_events(sid, base))

    out = ROOT / "data" / "demo_events.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for ev in all_events:
            f.write(json.dumps(ev) + "\n")

    with httpx.Client(timeout=30.0) as client:
        for i in range(0, len(all_events), 100):
            r = client.post(f"{API_URL}/events/ingest", json={"events": all_events[i : i + 100]})
            r.raise_for_status()
    print(f"Seeded {len(all_events)} events to {API_URL}")


if __name__ == "__main__":
    main()
