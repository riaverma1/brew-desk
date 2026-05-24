"""
Batch enrichment job — fills in Google data (photos, rating, hours) for places
that have never been enriched via the nearby search hot path.

Triggered via POST /regions/{region_id}/enrich (admin route).

Uses Place Details API directly since we already have place_ids from the resolver.
Rate-limited to _DETAILS_DELAY seconds between calls (~5 req/s) to stay well
under Google's default 100 req/s quota limit.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from services import google_places, supabase_client

logger = logging.getLogger(__name__)

_DETAILS_DELAY = 0.2   # 5 req/s — safe default, well under 100 req/s quota


async def enrich_unenriched_places(region_id: str, api_key: str, force: bool = False) -> dict:
    """
    Fetch Place Details for every place in the region with last_enriched_at IS NULL.
    Writes photos, primary_type, rating, user_rating_count, regular_opening_hours.

    force=True re-enriches all places regardless of last_enriched_at.
    Returns {"enriched": N, "failed": M, "skipped": K}.
    """
    rows = await (supabase_client.get_all_places_in_region(region_id) if force
                  else supabase_client.get_unenriched_places(region_id))
    total = len(rows)
    logger.info("Enrich job: %d unenriched places found for region %s", total, region_id)

    if not total:
        return {"enriched": 0, "failed": 0, "skipped": 0}

    enriched = 0
    failed = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        place_id = row["place_id"]
        details = await google_places.get_place_details(place_id, api_key)

        if details is None:
            failed += 1
            await asyncio.sleep(_DETAILS_DELAY)
            continue

        db_update: dict = {"last_enriched_at": now}
        if details.get("photo_urls"):
            db_update["photos"] = details["photo_urls"]
        if details.get("primary_type") is not None:
            db_update["primary_type"] = details["primary_type"]
        if details.get("rating") is not None:
            db_update["rating"] = details["rating"]
        if details.get("user_rating_count") is not None:
            db_update["user_rating_count"] = details["user_rating_count"]
        if details.get("regular_opening_hours") is not None:
            db_update["regular_opening_hours"] = details["regular_opening_hours"]

        await supabase_client.save_google_place_data(place_id, db_update)
        enriched += 1
        logger.debug("Enriched %s", place_id)

        await asyncio.sleep(_DETAILS_DELAY)

    summary = {"enriched": enriched, "failed": failed, "skipped": total - enriched - failed}
    logger.info("Enrich job complete for region %s: %s", region_id, summary)
    return summary
