"""Zone geometry helpers."""

from __future__ import annotations


def point_in_polygon(px: float, py: float, polygon: list[list[float]]) -> bool:
    """Ray casting; polygon coords are normalized 0-1."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def centroid_zone(
    cx_norm: float,
    cy_norm: float,
    zone_polygons: dict[str, list[list[float]]],
) -> str | None:
    for zone_id, poly in zone_polygons.items():
        if zone_id == "THRESHOLD":
            continue
        if point_in_polygon(cx_norm, cy_norm, poly):
            return zone_id
    return None


def crossed_line(
    prev_y: float,
    curr_y: float,
    line_y: float,
    direction: str,
) -> str | None:
    """Return ENTRY or EXIT when centroid crosses entry line."""
    if prev_y <= line_y < curr_y:
        return "ENTRY" if direction == "down" else "EXIT"
    if curr_y <= line_y < prev_y:
        return "EXIT" if direction == "down" else "ENTRY"
    return None
