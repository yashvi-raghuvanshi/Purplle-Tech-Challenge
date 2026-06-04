from __future__ import annotations

import logging
import os
from typing import Any

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.database import SessionLocal, db_available, init_db
from api.logging_middleware import StructuredLoggingMiddleware
from api.services.analytics import (
    compute_anomalies,
    compute_funnel,
    compute_heatmap,
    compute_metrics,
    health_status,
)
from api.services.ingest import ingest_batch

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("store_intel")

app = FastAPI(title="Store Intelligence API", version="1.0.0")
app.add_middleware(StructuredLoggingMiddleware)

DASHBOARD_STATIC = Path(__file__).resolve().parent.parent / "dashboard" / "static"
if DASHBOARD_STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=DASHBOARD_STATIC), name="dashboard-static")


def get_db():
    if not db_available():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "database_unavailable",
                "message": "Database is temporarily unavailable. Retry shortly.",
            },
        )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class IngestPayload(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", extra={"path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An unexpected error occurred."},
    )


@app.get("/")
@app.get("/dashboard")
def web_dashboard() -> FileResponse:
    index = DASHBOARD_STATIC / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(index)


@app.post("/events/ingest")
def ingest_events(
    payload: IngestPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if len(payload.events) > 500:
        raise HTTPException(
            status_code=400,
            detail={"error": "batch_too_large", "message": "Maximum 500 events per batch."},
        )
    request.state.event_count = len(payload.events)
    result = ingest_batch(db, payload.events)
    db.commit()
    status = "partial_success" if result["rejected"] else "success"
    return {"status": status, **result}


@app.get("/stores/{store_id}/metrics")
def store_metrics(store_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    data = compute_metrics(db, store_id)
    if data["total_events"] == 0:
        return {
            **data,
            "note": "zero_traffic",
            "unique_visitors": 0,
            "conversion_rate": 0.0,
        }
    return data


@app.get("/stores/{store_id}/funnel")
def store_funnel(store_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return compute_funnel(db, store_id)


@app.get("/stores/{store_id}/heatmap")
def store_heatmap(store_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return compute_heatmap(db, store_id)


@app.get("/stores/{store_id}/anomalies")
def store_anomalies(store_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return compute_anomalies(db, store_id)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    return health_status(db)
