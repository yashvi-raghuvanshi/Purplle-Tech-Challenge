# Apex Retail — Store Intelligence

End-to-end pipeline: **CCTV clips → person detection → structured events → REST API → live dashboard**.

Built for the Purplle Tech Challenge dataset (2 stores, short clips, POS sample CSV).

## Quick start (5 commands)

```bash
git clone <your-repo-url>
cd "Purplle Tech Challenge"
docker compose up -d --build
docker compose --profile demo run --rm seed
curl http://localhost:8000/health | jq
curl http://localhost:8000/stores/STORE_001/metrics | jq
open http://localhost:8000/dashboard
```

**Web dashboard:** http://localhost:8000/dashboard — live metrics, funnel, heatmap, and anomalies (refreshes every 2s).

## Run detection on your clips

```bash
# Local (requires Python 3.11 + deps)
pip install -r requirements-detection.txt
python -m detection.run --store STORE_001 --output data/events_store1.jsonl

# Ingest into API
pip install -r requirements.txt
uvicorn api.main:app --reload &
python -c "
import json, httpx
from pathlib import Path
events=[json.loads(l) for l in Path('data/events_store1.jsonl').read_text().splitlines() if l.strip()]
httpx.post('http://localhost:8000/events/ingest', json={'events': events}, timeout=60)
"

# Or via Docker profile (runs Store 1 pipeline + ingest)
docker compose --profile pipeline up detection
```

### Live / simulated real-time

```bash
python -m detection.run --store STORE_001 --realtime --ingest-url http://localhost:8000
# Open web UI (updates as events ingest):
open http://localhost:8000/dashboard
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/events/ingest` | Batch ingest (max 500), idempotent by `event_id` |
| GET | `/stores/{id}/metrics` | Visitors, conversion, dwell, queue, abandonment |
| GET | `/stores/{id}/funnel` | Entry → Zone → Billing → Purchase |
| GET | `/stores/{id}/heatmap` | Zone scores 0–100 + `data_confidence` |
| GET | `/stores/{id}/anomalies` | Active anomalies with severity |
| GET | `/health` | Service + per-store feed freshness |

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
# Integration assertions (API must be running):
pytest assertions.py -v
```

## Project layout

```
store_layout.json      # Zones, cameras, video paths, POS mapping
detection/             # YOLO + tracking + event emission
api/                   # FastAPI intelligence service
dashboard/             # Web UI (static/) + terminal fallback
scripts/seed_demo_events.py
assertions.py          # 10 sample API assertions
DESIGN.md / CHOICES.md
```

## Store IDs

- `STORE_001` — Store 1 folder (CAM 3 entry, CAM 1/2 zone, CAM 5 billing)
- `STORE_002` — Store 2 folder (entry 1/2, zone, billing)

Edit zone polygons in `store_layout.json` if detection counts need tuning for your footage.

## Submission checklist

- [ ] `docker compose up` works on a clean machine
- [ ] `pytest` ≥ 70% coverage on `api` + `shared`
- [ ] `DESIGN.md` + `CHOICES.md` included
- [ ] Git repo (do not commit challenge video licence outside private repo)
