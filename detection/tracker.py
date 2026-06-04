"""Simple IoU-based multi-object tracker."""

from __future__ import annotations

from dataclasses import dataclass, field


def iou(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    track_id: int
    bbox: tuple[float, float, float, float]
    centroid: tuple[float, float]
    age: int = 0
    hits: int = 0
    time_since_update: int = 0
    history: list[tuple[float, float]] = field(default_factory=list)
    is_staff: bool = False
    confidence: float = 0.0


class CentroidTracker:
    def __init__(self, max_disappeared: int = 30, iou_threshold: float = 0.3) -> None:
        self.max_disappeared = max_disappeared
        self.iou_threshold = iou_threshold
        self.tracks: dict[int, Track] = {}
        self._next_id = 1

    def update(
        self, detections: list[tuple[tuple[float, float, float, float], float, bool]]
    ) -> list[Track]:
        if not detections:
            for tid in list(self.tracks):
                self.tracks[tid].time_since_update += 1
                if self.tracks[tid].time_since_update > self.max_disappeared:
                    del self.tracks[tid]
            return list(self.tracks.values())

        unmatched = set(range(len(detections)))
        matched: dict[int, int] = {}

        for tid, track in self.tracks.items():
            best_iou, best_idx = 0.0, -1
            for idx in unmatched:
                box, _, _ = detections[idx]
                score = iou(track.bbox, box)
                if score > best_iou and score >= self.iou_threshold:
                    best_iou, best_idx = score, idx
            if best_idx >= 0:
                matched[tid] = best_idx
                unmatched.discard(best_idx)

        for tid, idx in matched.items():
            box, conf, is_staff = detections[idx]
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2
            track = self.tracks[tid]
            track.bbox = box
            track.centroid = (cx, cy)
            track.history.append((cx, cy))
            track.hits += 1
            track.time_since_update = 0
            track.confidence = conf
            track.is_staff = is_staff or track.is_staff

        for idx in unmatched:
            box, conf, is_staff = detections[idx]
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2
            tid = self._next_id
            self._next_id += 1
            self.tracks[tid] = Track(
                track_id=tid,
                bbox=box,
                centroid=(cx, cy),
                history=[(cx, cy)],
                confidence=conf,
                is_staff=is_staff,
            )

        for tid in list(self.tracks):
            if tid not in matched:
                self.tracks[tid].time_since_update += 1
                if self.tracks[tid].time_since_update > self.max_disappeared:
                    del self.tracks[tid]

        return list(self.tracks.values())
