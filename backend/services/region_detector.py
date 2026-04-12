"""
Determines whether a viewport is seeded, crawling, or cold
by checking overlapping regions in the DB.

Priority: seeded > crawling > cold
When multiple cold regions exist, picks the one with greatest bounding-box overlap.
"""
from __future__ import annotations

import logging

from models.place import MapBounds
from services import supabase_client

logger = logging.getLogger(__name__)

_STATUS_PRIORITY = {"seeded": 3, "crawling": 2, "cold": 1}


def _overlap_area(region: dict, bounds: MapBounds) -> float:
    """Compute approximate overlap area between a region bbox and a viewport."""
    lat_overlap = max(
        0.0,
        min(region["max_lat"], bounds.north) - max(region["min_lat"], bounds.south),
    )
    lng_overlap = max(
        0.0,
        min(region["max_lng"], bounds.east) - max(region["min_lng"], bounds.west),
    )
    return lat_overlap * lng_overlap


async def detect_region_for_viewport(
    bounds: MapBounds,
) -> tuple[str | None, str | None]:
    """
    Returns (region_id | None, status | None).

    - If any overlapping region is 'seeded', return the first seeded region.
    - If any are 'crawling', return the first crawling region.
    - If any are 'cold', return the cold region with greatest overlap.
    - If no regions overlap, return (None, None).
    """
    regions = await supabase_client.get_overlapping_regions(bounds)
    if not regions:
        return None, None

    seeded = [r for r in regions if r["status"] == "seeded"]
    if seeded:
        return seeded[0]["id"], "seeded"

    crawling = [r for r in regions if r["status"] == "crawling"]
    if crawling:
        return crawling[0]["id"], "crawling"

    cold = [r for r in regions if r["status"] == "cold"]
    if cold:
        best = max(cold, key=lambda r: _overlap_area(r, bounds))
        return best["id"], "cold"

    return None, None
