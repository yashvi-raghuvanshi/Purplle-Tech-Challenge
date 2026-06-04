"""CCTV detection pipeline: person detect → track → behavioural events."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from detection.staff_classifier import is_staff_uniform
from detection.tracker import CentroidTracker
from detection.zones import centroid_zone, crossed_line
from shared.layout import get_store, load_layout
from shared.schema import EventMetadata, EventType, StoreEvent, event_to_dict

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class VisitorState:
    visitor_id: str
    track_id: int
    session_seq: int = 0
    active: bool = True
    exited: bool = False
    zones_inside: set[str] = field(default_factory=set)
    dwell_accum_ms: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_dwell_emit: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    billing_joined: bool = False
    last_zone: str | None = None


class PersonDetector:
    def __init__(self, use_yolo: bool = True) -> None:
        self.use_yolo = use_yolo
        self._model = None
        if use_yolo:
            try:
                from ultralytics import YOLO

                self._model = YOLO("yolov8n.pt")
            except Exception:
                self.use_yolo = False
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame: np.ndarray) -> list[tuple[tuple[float, float, float, float], float]]:
        h, w = frame.shape[:2]
        results: list[tuple[tuple[float, float, float, float], float]] = []
        if self.use_yolo and self._model is not None:
            preds = self._model(frame, verbose=False, classes=[0])
            for r in preds:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    if conf >= 0.25:
                        results.append(((x1, y1, x2, y2), conf))
        else:
            boxes, weights = self.hog.detectMultiScale(
                frame, winStride=(8, 8), padding=(8, 8), scale=1.05
            )
            for (x, y, bw, bh), wt in zip(boxes, weights):
                conf = min(0.99, float(wt) / 2.0)
                if conf >= 0.3:
                    results.append(((x, y, x + bw, y + bh), conf))
        return results


def _frame_timestamp(base: datetime, frame_idx: int, fps: float) -> str:
    ts = base + timedelta(seconds=frame_idx / max(fps, 1.0))
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_visitor_id() -> str:
    return f"VIS_{uuid.uuid4().hex[:6]}"


class CameraPipeline:
    def __init__(
        self,
        store: dict[str, Any],
        camera: dict[str, Any],
        on_event: Callable[[dict[str, Any]], None] | None = None,
        realtime_factor: float = 1.0,
    ) -> None:
        self.store = store
        self.camera = camera
        self.on_event = on_event
        self.realtime_factor = realtime_factor
        self.detector = PersonDetector(use_yolo=True)
        self.tracker = CentroidTracker()
        self.track_to_visitor: dict[int, str] = {}
        self.visitor_states: dict[str, VisitorState] = {}
        self.reid_memory: dict[int, str] = {}  # track -> visitor after exit
        self.events: list[dict[str, Any]] = []
        self.global_session_seq: dict[str, int] = defaultdict(int)

    def _emit(self, event: StoreEvent) -> None:
        d = event_to_dict(event)
        self.events.append(d)
        if self.on_event:
            self.on_event(d)

    def _next_seq(self, visitor_id: str) -> int:
        self.global_session_seq[visitor_id] += 1
        return self.global_session_seq[visitor_id]

    def _assign_visitor(self, track_id: int, is_entry_cam: bool) -> str:
        if track_id in self.track_to_visitor:
            return self.track_to_visitor[track_id]
        if track_id in self.reid_memory:
            vid = self.reid_memory[track_id]
            self.track_to_visitor[track_id] = vid
            return vid
        vid = _new_visitor_id()
        self.track_to_visitor[track_id] = vid
        self.visitor_states[vid] = VisitorState(visitor_id=vid, track_id=track_id)
        return vid

    def process_video(self, video_path: Path, max_frames: int | None = None) -> list[dict[str, Any]]:
        role = self.camera.get("role", "floor")
        if role in ("storage",) or not self.camera.get("customer_traffic", True):
            return []

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        base = datetime.fromisoformat(
            self.store["base_timestamp"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)

        cam_id = self.camera["camera_id"]
        store_id = self.store["store_id"]
        zone_polys = self.store.get("zone_polygons", {}).get(cam_id, {})
        entry_cfg = self.store.get("entry_line", {}).get(cam_id)
        is_entry = role in ("entry", "entry_secondary")
        sku_map = {z["zone_id"]: z.get("sku_zone") for z in self.store["zones"]}

        frame_idx = 0
        queue_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if max_frames and frame_idx >= max_frames:
                break

            detections_raw = self.detector.detect(frame)
            detections = []
            for box, conf in detections_raw:
                staff = is_staff_uniform(frame, box)
                detections.append((box, conf, staff))

            tracks = self.tracker.update(detections)
            ts = _frame_timestamp(base, frame_idx, fps)

            for track in tracks:
                cx, cy = track.centroid
                cx_n, cy_n = cx / width, cy / height
                visitor_id = self._assign_visitor(track.track_id, is_entry)
                state = self.visitor_states[visitor_id]

                if len(track.history) >= 2:
                    _, prev_y = track.history[-2]
                    prev_y_n = prev_y / height
                    if is_entry and entry_cfg:
                        cross = crossed_line(
                            prev_y_n,
                            cy_n,
                            entry_cfg["y_norm"],
                            entry_cfg.get("inbound_direction", "down"),
                        )
                        if cross == "ENTRY" and visitor_id not in self.reid_memory.values():
                            if state.exited:
                                self._emit(
                                    StoreEvent(
                                        event_id=str(uuid.uuid4()),
                                        store_id=store_id,
                                        camera_id=cam_id,
                                        visitor_id=visitor_id,
                                        event_type=EventType.REENTRY,
                                        timestamp=ts,
                                        confidence=track.confidence,
                                        is_staff=track.is_staff,
                                        metadata=EventMetadata(
                                            session_seq=self._next_seq(visitor_id)
                                        ),
                                    )
                                )
                                state.exited = False
                            else:
                                self._emit(
                                    StoreEvent(
                                        event_id=str(uuid.uuid4()),
                                        store_id=store_id,
                                        camera_id=cam_id,
                                        visitor_id=visitor_id,
                                        event_type=EventType.ENTRY,
                                        timestamp=ts,
                                        confidence=track.confidence,
                                        is_staff=track.is_staff,
                                        metadata=EventMetadata(
                                            session_seq=self._next_seq(visitor_id)
                                        ),
                                    )
                                )
                        elif cross == "EXIT":
                            state.exited = True
                            self.reid_memory[track.track_id] = visitor_id
                            self._emit(
                                StoreEvent(
                                    event_id=str(uuid.uuid4()),
                                    store_id=store_id,
                                    camera_id=cam_id,
                                    visitor_id=visitor_id,
                                    event_type=EventType.EXIT,
                                    timestamp=ts,
                                    confidence=track.confidence,
                                    is_staff=track.is_staff,
                                    metadata=EventMetadata(
                                        session_seq=self._next_seq(visitor_id)
                                    ),
                                )
                            )

                zone_id = centroid_zone(cx_n, cy_n, zone_polys) if zone_polys else None
                if zone_id and zone_id != "THRESHOLD":
                    frame_ms = int(1000 / max(fps, 1))
                    state.dwell_accum_ms[zone_id] += frame_ms

                    if zone_id not in state.zones_inside:
                        state.zones_inside.add(zone_id)
                        self._emit(
                            StoreEvent(
                                event_id=str(uuid.uuid4()),
                                store_id=store_id,
                                camera_id=cam_id,
                                visitor_id=visitor_id,
                                event_type=EventType.ZONE_ENTER,
                                timestamp=ts,
                                zone_id=zone_id,
                                confidence=track.confidence,
                                is_staff=track.is_staff,
                                metadata=EventMetadata(
                                    sku_zone=sku_map.get(zone_id),
                                    session_seq=self._next_seq(visitor_id),
                                ),
                            )
                        )

                    if state.dwell_accum_ms[zone_id] - state.last_dwell_emit[zone_id] >= 30000:
                        state.last_dwell_emit[zone_id] = state.dwell_accum_ms[zone_id]
                        self._emit(
                            StoreEvent(
                                event_id=str(uuid.uuid4()),
                                store_id=store_id,
                                camera_id=cam_id,
                                visitor_id=visitor_id,
                                event_type=EventType.ZONE_DWELL,
                                timestamp=ts,
                                zone_id=zone_id,
                                dwell_ms=30000,
                                confidence=track.confidence,
                                is_staff=track.is_staff,
                                metadata=EventMetadata(
                                    sku_zone=sku_map.get(zone_id),
                                    session_seq=self._next_seq(visitor_id),
                                ),
                            )
                        )

                    if zone_id == "BILLING":
                        queue_count = sum(
                            1
                            for t in self.tracker.tracks.values()
                            if centroid_zone(
                                t.centroid[0] / width,
                                t.centroid[1] / height,
                                zone_polys,
                            )
                            == "BILLING"
                        )
                        if queue_count > 0 and not state.billing_joined:
                            state.billing_joined = True
                            self._emit(
                                StoreEvent(
                                    event_id=str(uuid.uuid4()),
                                    store_id=store_id,
                                    camera_id=cam_id,
                                    visitor_id=visitor_id,
                                    event_type=EventType.BILLING_QUEUE_JOIN,
                                    timestamp=ts,
                                    zone_id=zone_id,
                                    confidence=track.confidence,
                                    is_staff=track.is_staff,
                                    metadata=EventMetadata(
                                        queue_depth=queue_count,
                                        sku_zone=sku_map.get(zone_id),
                                        session_seq=self._next_seq(visitor_id),
                                    ),
                                )
                            )

                    state.last_zone = zone_id
                elif state.last_zone and state.last_zone in state.zones_inside:
                    left = state.last_zone
                    state.zones_inside.discard(left)
                    self._emit(
                        StoreEvent(
                            event_id=str(uuid.uuid4()),
                            store_id=store_id,
                            camera_id=cam_id,
                            visitor_id=visitor_id,
                            event_type=EventType.ZONE_EXIT,
                            timestamp=ts,
                            zone_id=left,
                            confidence=track.confidence,
                            is_staff=track.is_staff,
                            metadata=EventMetadata(
                                sku_zone=sku_map.get(left),
                                session_seq=self._next_seq(visitor_id),
                            ),
                        )
                    )
                    if left == "BILLING" and state.billing_joined:
                        self._emit(
                            StoreEvent(
                                event_id=str(uuid.uuid4()),
                                store_id=store_id,
                                camera_id=cam_id,
                                visitor_id=visitor_id,
                                event_type=EventType.BILLING_QUEUE_ABANDON,
                                timestamp=ts,
                                zone_id=left,
                                confidence=track.confidence,
                                is_staff=track.is_staff,
                                metadata=EventMetadata(
                                    session_seq=self._next_seq(visitor_id)
                                ),
                            )
                        )
                        state.billing_joined = False
                    state.last_zone = None

            frame_idx += 1

        cap.release()
        return self.events


def run_store_pipeline(
    store_id: str,
    root: Path | None = None,
    output_path: Path | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    ingest_url: str | None = None,
) -> list[dict[str, Any]]:
    layout = load_layout()
    store = get_store(layout, store_id)
    if not store:
        raise ValueError(f"Unknown store: {store_id}")

    base = root or ROOT
    all_events: list[dict[str, Any]] = []

    for camera in store["cameras"]:
        rel = camera["video_path"]
        video = base / rel
        if not video.exists():
            continue
        pipeline = CameraPipeline(store, camera, on_event=on_event)
        events = pipeline.process_video(video)
        all_events.extend(events)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            for ev in all_events:
                f.write(json.dumps(ev) + "\n")

    if ingest_url and all_events:
        import httpx

        batch_size = 100
        with httpx.Client(timeout=60.0) as client:
            for i in range(0, len(all_events), batch_size):
                batch = all_events[i : i + batch_size]
                client.post(f"{ingest_url.rstrip('/')}/events/ingest", json={"events": batch})

    return all_events
