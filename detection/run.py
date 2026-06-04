#!/usr/bin/env python3
"""CLI entrypoint for detection pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from detection.pipeline import run_store_pipeline

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Store Intelligence detection pipeline")
    parser.add_argument("--store", required=True, help="Store ID e.g. STORE_001")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "events.jsonl")
    parser.add_argument("--ingest-url", default=None, help="API base URL for live ingest")
    parser.add_argument("--realtime", action="store_true", help="Stream events as processed")
    args = parser.parse_args()

    buffer: list[dict] = []
    http_client = None

    if args.realtime and args.ingest_url:
        import httpx

        http_client = httpx.Client(timeout=30.0)

        def on_event(ev: dict) -> None:
            buffer.append(ev)
            if len(buffer) >= 10:
                http_client.post(
                    f"{args.ingest_url.rstrip('/')}/events/ingest",
                    json={"events": buffer.copy()},
                )
                buffer.clear()

    events = run_store_pipeline(
        args.store,
        output_path=args.output,
        on_event=on_event if args.realtime and args.ingest_url else None,
        ingest_url=args.ingest_url if not args.realtime else None,
    )
    if http_client and buffer:
        http_client.post(
            f"{args.ingest_url.rstrip('/')}/events/ingest",
            json={"events": buffer},
        )
        http_client.close()

    print(f"Emitted {len(events)} events -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
