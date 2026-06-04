#!/usr/bin/env python3
"""Terminal live dashboard polling store metrics."""

from __future__ import annotations

import os
import sys
import time

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000")
STORE_ID = os.getenv("STORE_ID", "STORE_001")
POLL_SEC = float(os.getenv("POLL_SEC", "2"))


def render(metrics: dict) -> str:
    return (
        f"\n{'=' * 50}\n"
        f" LIVE STORE METRICS — {metrics.get('store_id', STORE_ID)}\n"
        f"{'=' * 50}\n"
        f" Unique visitors today : {metrics.get('unique_visitors', 0)}\n"
        f" Conversion rate       : {metrics.get('conversion_rate', 0):.2%}\n"
        f" Queue depth           : {metrics.get('queue_depth', 0)}\n"
        f" Abandonment rate      : {metrics.get('abandonment_rate', 0):.2%}\n"
        f" Customer events       : {metrics.get('customer_events', 0)}\n"
        f"{'=' * 50}\n"
    )


def main() -> int:
    print(f"Dashboard → {API_URL} store={STORE_ID}")
    with httpx.Client(timeout=10.0) as client:
        while True:
            try:
                r = client.get(f"{API_URL}/stores/{STORE_ID}/metrics")
                r.raise_for_status()
                sys.stdout.write(render(r.json()))
                sys.stdout.flush()
            except httpx.HTTPError as exc:
                sys.stdout.write(f"\n[error] {exc}\n")
            time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
