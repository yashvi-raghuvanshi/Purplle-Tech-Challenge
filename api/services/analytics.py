from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.config import CONVERSION_WINDOW_MINUTES
from api.models import EventRecord
from api.pos_loader import POSTransaction, load_pos_for_store


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class VisitorSession:
    visitor_id: str
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    zones_visited: set[str] = field(default_factory=set)
    billing_joined: bool = False
    billing_abandoned: bool = False
    converted: bool = False
    is_staff: bool = False
    reentry: bool = False


def _customer_events(events: list[EventRecord]) -> list[EventRecord]:
    return [e for e in events if not e.is_staff]


def build_sessions(events: list[EventRecord]) -> list[VisitorSession]:
    """Build visitor sessions from ENTRY/EXIT/REENTRY events."""
    by_visitor: dict[str, list[EventRecord]] = defaultdict(list)
    for e in _customer_events(events):
        by_visitor[e.visitor_id].append(e)

    sessions: list[VisitorSession] = []
    for visitor_id, visitor_events in by_visitor.items():
        visitor_events.sort(key=lambda x: x.timestamp)
        current: VisitorSession | None = None
        for ev in visitor_events:
            if ev.event_type == "ENTRY":
                if current and current.entry_time and not current.exit_time:
                    sessions.append(current)
                current = VisitorSession(visitor_id=visitor_id, entry_time=ev.timestamp)
            elif ev.event_type == "REENTRY" and current:
                current.reentry = True
                current.entry_time = ev.timestamp
            elif ev.event_type == "EXIT" and current:
                current.exit_time = ev.timestamp
                sessions.append(current)
                current = None
            elif current:
                if ev.event_type in ("ZONE_ENTER", "ZONE_DWELL") and ev.zone_id:
                    current.zones_visited.add(ev.zone_id)
                if ev.event_type == "BILLING_QUEUE_JOIN":
                    current.billing_joined = True
                if ev.event_type == "BILLING_QUEUE_ABANDON":
                    current.billing_abandoned = True
        if current and current.entry_time:
            sessions.append(current)
    return sessions


def correlate_conversions(
    sessions: list[VisitorSession],
    pos_txns: list[POSTransaction],
    billing_events: list[EventRecord],
) -> None:
    window = timedelta(minutes=CONVERSION_WINDOW_MINUTES)
    for session in sessions:
        if not session.billing_joined and not any(
            e.zone_id == "BILLING" for e in billing_events if e.visitor_id == session.visitor_id
        ):
            billing_visits = [
                e
                for e in billing_events
                if e.visitor_id == session.visitor_id
                and e.event_type in ("ZONE_ENTER", "BILLING_QUEUE_JOIN")
                and e.zone_id == "BILLING"
            ]
            if billing_visits:
                session.billing_joined = True

        session_start = _aware(session.entry_time) if session.entry_time else None
        if not session_start:
            continue
        session_end = _aware(session.exit_time) if session.exit_time else (session_start + timedelta(hours=2))
        for txn in pos_txns:
            txn_ts = _aware(txn.timestamp)
            if session_start <= txn_ts <= session_end + window:
                if session.billing_joined or session.zones_visited:
                    session.converted = True
                    break


def get_store_events(
    session: Session, store_id: str, since: datetime | None = None
) -> list[EventRecord]:
    q = session.query(EventRecord).filter(EventRecord.store_id == store_id)
    if since:
        q = q.filter(EventRecord.timestamp >= since)
    return q.order_by(EventRecord.timestamp).all()


def compute_metrics(session: Session, store_id: str) -> dict[str, Any]:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    events = get_store_events(session, store_id, since=today)
    customer = _customer_events(events)
    sessions = build_sessions(events)
    pos_txns = load_pos_for_store(store_id)
    billing_events = [e for e in customer if e.zone_id == "BILLING" or "BILLING" in e.event_type]
    correlate_conversions(sessions, pos_txns, billing_events)

    unique_visitors = len({s.visitor_id for s in sessions if s.entry_time})
    converted = sum(1 for s in sessions if s.converted)
    conversion_rate = (converted / unique_visitors) if unique_visitors else 0.0

    dwell_by_zone: dict[str, list[int]] = defaultdict(list)
    for e in customer:
        if e.event_type == "ZONE_DWELL" and e.zone_id:
            dwell_by_zone[e.zone_id].append(e.dwell_ms)

    avg_dwell_per_zone = {
        z: (sum(vals) / len(vals) / 1000.0) if vals else 0.0
        for z, vals in dwell_by_zone.items()
    }

    queue_depths = []
    for e in customer:
        if e.event_type == "BILLING_QUEUE_JOIN":
            meta = json.loads(e.metadata_json or "{}")
            if meta.get("queue_depth") is not None:
                queue_depths.append(meta["queue_depth"])
    queue_depth = max(queue_depths) if queue_depths else 0

    billing_sessions = [s for s in sessions if s.billing_joined]
    abandoned = sum(1 for s in billing_sessions if s.billing_abandoned and not s.converted)
    abandonment_rate = (abandoned / len(billing_sessions)) if billing_sessions else 0.0

    return {
        "store_id": store_id,
        "date": today.date().isoformat(),
        "unique_visitors": unique_visitors,
        "conversion_rate": round(conversion_rate, 4),
        "converted_visitors": converted,
        "avg_dwell_seconds_per_zone": {
            k: round(v, 2) for k, v in avg_dwell_per_zone.items()
        },
        "queue_depth": queue_depth,
        "abandonment_rate": round(abandonment_rate, 4),
        "total_events": len(events),
        "customer_events": len(customer),
    }


def compute_funnel(session: Session, store_id: str) -> dict[str, Any]:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    events = get_store_events(session, store_id, since=today)
    sessions = build_sessions(events)
    pos_txns = load_pos_for_store(store_id)
    correlate_conversions(sessions, pos_txns, events)

    # Re-entry: count session once at funnel entry using first ENTRY per visitor
    seen_visitors: set[str] = set()
    entry_count = 0
    min_dt = datetime.min.replace(tzinfo=timezone.utc)
    for s in sorted(sessions, key=lambda x: _aware(x.entry_time) if x.entry_time else min_dt):
        if s.visitor_id in seen_visitors and not s.reentry:
            continue
        if s.reentry:
            continue  # re-entries do not inflate entry count
        seen_visitors.add(s.visitor_id)
        entry_count += 1

    zone_visit = sum(1 for s in sessions if s.zones_visited)
    billing = sum(1 for s in sessions if s.billing_joined)
    purchase = sum(1 for s in sessions if s.converted)

    stages = [
        ("Entry", entry_count),
        ("Zone Visit", zone_visit),
        ("Billing Queue", billing),
        ("Purchase", purchase),
    ]
    funnel = []
    prev = None
    for name, count in stages:
        drop = None
        if prev is not None and prev > 0:
            drop = round(100.0 * (1 - count / prev), 2)
        funnel.append({"stage": name, "count": count, "drop_off_pct": drop})
        prev = count

    return {"store_id": store_id, "funnel": funnel, "session_count": len(sessions)}


def compute_heatmap(session: Session, store_id: str) -> dict[str, Any]:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    events = get_store_events(session, store_id, since=today)
    sessions = build_sessions(events)
    customer = _customer_events(events)

    visit_freq: dict[str, int] = defaultdict(int)
    dwell_totals: dict[str, int] = defaultdict(int)
    for e in customer:
        if e.zone_id and e.event_type in ("ZONE_ENTER", "ZONE_DWELL"):
            visit_freq[e.zone_id] += 1
            dwell_totals[e.zone_id] += e.dwell_ms

    max_freq = max(visit_freq.values()) if visit_freq else 1
    max_dwell = max(dwell_totals.values()) if dwell_totals else 1

    zones = []
    for zone_id in set(list(visit_freq.keys()) + list(dwell_totals.keys())):
        freq_norm = round(100.0 * visit_freq.get(zone_id, 0) / max_freq, 2)
        dwell_norm = round(100.0 * dwell_totals.get(zone_id, 0) / max_dwell, 2)
        zones.append(
            {
                "zone_id": zone_id,
                "visit_frequency": freq_norm,
                "avg_dwell_normalized": dwell_norm,
                "visit_count": visit_freq.get(zone_id, 0),
            }
        )

    return {
        "store_id": store_id,
        "zones": zones,
        "data_confidence": len(sessions) >= 20,
        "session_count": len(sessions),
    }


def compute_anomalies(session: Session, store_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    events = get_store_events(session, store_id, since=today - timedelta(days=7))
    customer = _customer_events(events)
    anomalies: list[dict[str, Any]] = []

    recent_queue = [
        json.loads(e.metadata_json or "{}").get("queue_depth", 0)
        for e in customer
        if e.event_type == "BILLING_QUEUE_JOIN"
        and _aware(e.timestamp) >= now - timedelta(minutes=15)
    ]
    if recent_queue and max(recent_queue) >= 4:
        anomalies.append(
            {
                "type": "queue_spike",
                "severity": "WARN",
                "message": f"Billing queue depth peaked at {max(recent_queue)}",
                "suggested_action": "Open additional billing counter or deploy floor staff to queue.",
            }
        )

    metrics_today = compute_metrics(session, store_id)
    conv = metrics_today["conversion_rate"]
    if conv < 0.05 and metrics_today["unique_visitors"] >= 3:
        anomalies.append(
            {
                "type": "conversion_drop",
                "severity": "CRITICAL",
                "message": f"Conversion rate {conv:.1%} is below baseline",
                "suggested_action": "Review staffing at billing and check POS connectivity.",
            }
        )

    thirty_min_ago = now - timedelta(minutes=30)
    zone_events = [
        e
        for e in customer
        if e.event_type in ("ZONE_ENTER", "ZONE_DWELL")
        and _aware(e.timestamp) >= thirty_min_ago
        and e.zone_id
        and e.zone_id not in ("THRESHOLD", "BILLING")
    ]
    if not zone_events and metrics_today["unique_visitors"] == 0:
        anomalies.append(
            {
                "type": "dead_zone",
                "severity": "INFO",
                "message": "No zone visits in the last 30 minutes",
                "suggested_action": "Verify cameras are online; may be legitimate low-traffic period.",
            }
        )
    elif not zone_events:
        anomalies.append(
            {
                "type": "dead_zone",
                "severity": "WARN",
                "message": "Floor zones show no visits in 30 minutes despite prior traffic",
                "suggested_action": "Check floor camera alignment and detection pipeline health.",
            }
        )

    return {"store_id": store_id, "anomalies": anomalies, "checked_at": now.isoformat()}


def health_status(session: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stale_threshold = timedelta(minutes=10)
    stores: dict[str, Any] = {}
    warnings: list[str] = []

    store_ids = [
        row[0]
        for row in session.query(EventRecord.store_id).distinct().all()
    ]
    if not store_ids:
        store_ids = ["STORE_001", "STORE_002"]

    for sid in store_ids:
        last_ts = (
            session.query(func.max(EventRecord.timestamp))
            .filter(EventRecord.store_id == sid)
            .scalar()
        )
        lag_minutes = None
        stale = False
        if last_ts:
            lag = now - _aware(last_ts)
            lag_minutes = round(lag.total_seconds() / 60, 2)
            stale = lag > stale_threshold
        else:
            stale = True
        if stale:
            warnings.append(f"STALE_FEED:{sid}")
        stores[sid] = {
            "last_event_timestamp": last_ts.isoformat() if last_ts else None,
            "lag_minutes": lag_minutes,
            "stale": stale,
        }

    status = "degraded" if warnings else "healthy"
    return {
        "status": status,
        "timestamp": now.isoformat(),
        "stores": stores,
        "warnings": warnings,
    }
