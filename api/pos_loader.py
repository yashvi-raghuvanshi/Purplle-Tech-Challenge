"""Aggregate POS line items into transaction-level records per store."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from api.config import POS_CSV_PATH
from shared.layout import LAYOUT_PATH, load_layout


@dataclass
class POSTransaction:
    store_id: str
    transaction_id: str
    timestamp: datetime
    basket_value_inr: float


def _parse_pos_row(row: dict[str, str], pos_store_id: str) -> POSTransaction | None:
    if row.get("store_id") != pos_store_id:
        return None
    date_str = row.get("order_date", "")
    time_str = row.get("order_time", "")
    order_id = row.get("order_id", "")
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc)
        amount = float(row.get("total_amount", 0))
    except (ValueError, TypeError):
        return None
    return POSTransaction(
        store_id=pos_store_id,
        transaction_id=f"TXN_{order_id}",
        timestamp=dt,
        basket_value_inr=amount,
    )


def load_pos_for_store(store_id: str, csv_path: str | None = None) -> list[POSTransaction]:
    layout = load_layout(Path(LAYOUT_PATH))
    store = next((s for s in layout["stores"] if s["store_id"] == store_id), None)
    if not store:
        return []
    pos_store_id = store.get("pos_store_id", "ST1008")
    path = Path(csv_path or POS_CSV_PATH)
    if not path.exists():
        return []

    grouped: dict[tuple[str, str, str], float] = defaultdict(float)
    for row in csv.DictReader(path.open(encoding="utf-8")):
        txn = _parse_pos_row(row, pos_store_id)
        if not txn:
            continue
        key = (txn.store_id, txn.transaction_id, txn.timestamp.isoformat())
        grouped[key] += txn.basket_value_inr

    results: list[POSTransaction] = []
    for (sid, tid, ts_iso), total in grouped.items():
        results.append(
            POSTransaction(
                store_id=sid,
                transaction_id=tid,
                timestamp=datetime.fromisoformat(ts_iso),
                basket_value_inr=total,
            )
        )
    return sorted(results, key=lambda t: t.timestamp)
