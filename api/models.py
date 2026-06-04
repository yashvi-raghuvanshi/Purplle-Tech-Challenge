from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base


class EventRecord(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    store_id: Mapped[str] = mapped_column(String(32), index=True)
    camera_id: Mapped[str] = mapped_column(String(32))
    visitor_id: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    zone_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    dwell_ms: Mapped[int] = mapped_column(Integer, default=0)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (Index("ix_store_ts", "store_id", "timestamp"),)


class DailyMetricSnapshot(Base):
    """Rolling 7-day baselines for anomaly detection."""

    __tablename__ = "daily_metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(String(32), index=True)
    metric_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    conversion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    unique_visitors: Mapped[int] = mapped_column(Integer, default=0)
