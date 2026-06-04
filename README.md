# Store Customer Detection

Built for the Purplle Tech Challenge Round 2.

## Quick Start (Docker)

```bash
git clone https://github.com/yashvi-raghuvanshi/Purplle-Tech-Challenge
cd "Purplle Tech Challenge"
docker compose up -d --build
docker compose --profile demo run --rm seed
```
## Verify
``` bash
curl http://localhost:8000/health

curl http://localhost:8000/stores/STORE_001/metrics
```

### Open Web dashboard in browser:
http://localhost:8000/dashboard

## Run Tests
```bash
pip install -r requirements.txt
pytest tests/ -v


# Run Detection (optional)
pip install -r requirements-detection.txt
python -m detection.run --store STORE_001 --output data/events_store1.jsonl
```

## Advanced
``` bash
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


### Live / simulated real-time

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
