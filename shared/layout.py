"""Load store layout configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LAYOUT_PATH = ROOT / "store_layout.json"


def load_layout(path: Path | None = None) -> dict[str, Any]:
    with open(path or LAYOUT_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_store(layout: dict[str, Any], store_id: str) -> dict[str, Any] | None:
    for store in layout["stores"]:
        if store["store_id"] == store_id:
            return store
    return None


def zone_sku_map(store: dict[str, Any]) -> dict[str, str | None]:
    return {z["zone_id"]: z.get("sku_zone") for z in store["zones"]}
