"""Heuristic staff detection via uniform-like upper-body color."""

from __future__ import annotations

import numpy as np


def is_staff_uniform(frame: np.ndarray, bbox: tuple[float, float, float, float]) -> bool:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    x1i, y1i = max(0, int(x1)), max(0, int(y1))
    x2i, y2i = min(w, int(x2)), min(h, int(y2))
    if x2i <= x1i or y2i <= y1i:
        return False
    roi = frame[y1i:y1i + int((y2i - y1i) * 0.4), x1i:x2i]
    if roi.size == 0:
        return False
    hsv = __import__("cv2").cvtColor(roi, __import__("cv2").COLOR_BGR2HSV)
    # Staff uniforms often solid dark blue / teal / black in these clips
    blue_mask = (hsv[:, :, 0] > 90) & (hsv[:, :, 0] < 130) & (hsv[:, :, 1] > 40)
    dark_mask = hsv[:, :, 2] < 80
    ratio = (np.count_nonzero(blue_mask) + np.count_nonzero(dark_mask)) / hsv[:, :, 0].size
    return ratio > 0.35
