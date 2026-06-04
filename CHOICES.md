# Engineering Choices

## 1. Detection model: YOLOv8n (+ HOG fallback)

**Options considered**

| Option | Pros | Cons |
|--------|------|------|
| YOLOv8n (Ultralytics) | Fast, strong person class, easy COCO weights | Requires torch; larger Docker image |
| RT-DETR | Accurate | Heavier, slower on CPU |
| OpenCV HOG | No GPU, tiny deps | Weak on occlusion/crowds |
| VLM per frame | Flexible labels | Slow, costly, non-deterministic |

**What AI suggested**  
Use YOLOv8 + ByteTrack as the default retail stack.

**What I chose and why**  
**YOLOv8n** for person detection with a **lightweight IoU tracker** (not full ByteTrack) to limit dependencies and keep the pipeline understandable in a take-home review. If Ultralytics fails to load, **HOG** runs so Docker/CI still produces events. For your short clips (<3 min), this is sufficient; full 20-minute clips would use the same code with longer runtime.

**VLM evaluation**  
I tested the idea of a VLM prompt: *"Is this bounding box a store employee in uniform? yes/no"*. On blurred CCTV it was inconsistent and added latency. I rejected it for production path and kept HSV uniform heuristic; staff events remain in the stream with `is_staff=true` for metric exclusion.

---

## 2. Event schema design

**Options considered**

- **Single flat schema** (challenge canonical) — one JSON shape for ingest and analytics.
- **Multi-schema like sample file** (`entry` vs `zone_entered` vs `queue_completed`) — matches raw detector output but needs heavy normalisation.
- **Protobuf/Kafka** — good at scale, overkill here.

**What AI suggested**  
Normalise everything to the challenge `StoreEvent` schema at the pipeline boundary.

**What I chose and why**  
Emit **only canonical events** (`ENTRY`, `ZONE_DWELL`, `BILLING_QUEUE_JOIN`, etc.) from `detection/pipeline.py`. Rationale:

- API tests and assertions target one schema.
- `event_id` UUID + `visitor_id` session token support idempotency and funnel logic.
- `metadata.queue_depth` and `session_seq` avoid nullable top-level sprawl.
- Low-confidence detections are **included** with real `confidence` (never silently dropped).

---

## 3. API architecture: FastAPI + SQLAlchemy + session-based analytics

**Options considered**

- **Stream processor** (Flink/Kafka) pre-aggregating metrics.
- **OLAP queries** on raw events per request.
- **Materialised views** updated on ingest.

**What AI suggested**  
Precompute rolling metrics on every ingest event.

**What I chose and why**  
**Compute on read** from SQLite for simplicity and correct behaviour with partial batches. Ingest stays O(n) per batch; analytics rebuild sessions in memory from today's events — fine for demo scale and easy to test. Structured logging and 503 on DB failure match production expectations without operating Kafka locally.

**POS correlation**  
Time-window + store-level matching (no `customer_id`), per brief: billing presence within 5 minutes of POS timestamp counts as conversion.
