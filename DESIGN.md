# Store Intelligence — Architecture

## Overview

This system turns anonymised retail CCTV into live store analytics. It has four layers:

1. **Detection pipeline** (`detection/`) — reads MP4 clips, detects people (YOLOv8n with HOG fallback), tracks them, classifies staff heuristically, and emits canonical JSON events.
2. **Event ingest** — `POST /events/ingest` validates events (Pydantic), deduplicates by `event_id`, and persists to SQLite.
3. **Intelligence API** (`api/`) — computes metrics, funnel, heatmap, and anomalies from stored events, correlated with POS aggregates.
4. **Live dashboard** — web UI at `/dashboard` (polls API every 2s); terminal script in `dashboard/live_dashboard.py` as fallback.

```
CCTV clips → Detection → JSONL / HTTP ingest → SQLite → REST API → Dashboard
                     ↘ store_layout.json (zones, cameras, polygons)
                     ↘ POS CSV (conversion correlation)
```

## Detection design

- **Per-camera processing**: Each camera in `store_layout.json` maps to one video file. Storage-only angles can be marked `customer_traffic: false` (none in our two-store dataset; CAM 1 in Store 1 is a floor zone camera).
- **Tracking**: IoU-based `CentroidTracker` assigns stable track IDs per clip.
- **Visitor sessions**: Entry cameras assign `visitor_id` on `ENTRY`. `EXIT` closes the session; a later crossing emits `REENTRY` instead of a second `ENTRY`.
- **Zones**: Normalised polygons per camera in `store_layout.json`. Centroid-in-polygon triggers `ZONE_ENTER` / `ZONE_EXIT` / `ZONE_DWELL` (30s cadence).
- **Billing**: `BILLING_QUEUE_JOIN` includes `metadata.queue_depth` (count of tracks in billing polygon). Abandon emits when leaving billing without conversion.
- **Staff**: Upper-body HSV heuristic flags uniforms; events still emitted with `is_staff=true` but API metrics exclude them.
- **Timestamps**: `base_timestamp` from layout + frame index / FPS.

## API design

- **FastAPI** with structured logging middleware (`trace_id`, `store_id`, `endpoint`, `latency_ms`, `event_count`, `status_code`).
- **Session model** for funnel: built from ENTRY/EXIT/REENTRY and zone events; re-entries do not inflate entry counts.
- **POS correlation**: Line-level CSV aggregated by order; visitors in billing within 5 minutes of transaction time count as converted.
- **Anomalies**: Queue spike (depth ≥ 4), conversion drop, dead zone (no floor visits 30 min).
- **Health**: Per-store last event time; `STALE_FEED` warning if lag > 10 minutes.

## Deployment

`docker compose up` starts the API on port 8000. Optional profiles:

- `docker compose --profile demo up` — seeds demo events after API is healthy.
- `docker compose --profile pipeline up` — runs detection on Store 1 and ingests.
- `docker compose --profile dashboard up` — live terminal metrics.

## Data mapping (your dataset)

| Folder | `store_id` | Cameras |
|--------|------------|---------|
| Store 1 | `STORE_001` | entry, 2 zone, billing |
| Store 2 | `STORE_002` | 2 entry, zone, billing |

POS file uses `ST1008`; both stores map to it via `pos_store_id` in layout.

## AI-Assisted Decisions

1. **Zone polygons as normalised coordinates** — An LLM suggested drawing zones interactively per clip. I overrode with configurable polygons in `store_layout.json` so the same pipeline runs in Docker without a GUI and reviewers can tune zones without recompiling.
2. **SQLite for the API database** — AI recommended Postgres for production. I chose SQLite for zero-dependency `docker compose up` while keeping SQLAlchemy so swapping `DATABASE_URL` to Postgres is trivial.
3. **Staff via colour heuristic vs VLM** — A VLM prompt was drafted for uniform detection; on blurred CCTV it would be slow and non-deterministic. I kept the heuristic for reproducible scoring runs and documented the VLM trade-off in `CHOICES.md`.
