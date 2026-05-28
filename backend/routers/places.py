"""
POST /places/nearby-search — hot-path endpoint for all map pan events.

Display uses viewport bounds (not the nearby circle radius):
  Query the places table by lat/lng bounds — every WFH spot we know about
  in the visible area shows up regardless of whether Google's Nearby Search
  included it in the top 20 for a 1500m circle.

Enrichment uses the Nearby Search:
  Runs in parallel. Any of our DB places that also appear in the nearby
  results get fresh photos/rating/hours written back in a background task.
  Places outside the nearby radius still show — they just keep cached data.

Steps:
  1. asyncio.gather: Google Nearby Search + region detection + DB bounds query
  2. Enrich DB places that appeared in nearby results (background task)
  3. Merge live Google data into response where available
  4. If cold region: trigger seed job (background, non-blocking)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends

from config import Settings, get_settings
from models.place import NearbySearchRequest, NearbySearchResponse, PlacePinResponse
from services import google_places, region_detector, supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/places", tags=["places"])


@router.post("/nearby-search", response_model=NearbySearchResponse)
async def nearby_search(
    req: NearbySearchRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> NearbySearchResponse:
    # Step 1: all three run in parallel
    nearby_results, (region_id, status), db_places = await asyncio.gather(
        google_places.nearby_search_parallel(
            req.lat,
            req.lng,
            settings.nearby_search_radius_meters,
            settings.google_places_api_key,
        ),
        region_detector.detect_region_for_viewport(req.bounds),
        supabase_client.get_places_in_bounds(req.bounds),
    )

    logger.info(
        "nearby-search: bounds query returned %d DB places | "
        "nearby search returned %d Google places | region=%s status=%s",
        len(db_places), len(nearby_results), region_id, status,
    )

    # Trigger seed for cold regions regardless of results
    if status == "cold" and region_id:
        from background.seed_job import trigger_seed
        background_tasks.add_task(trigger_seed, region_id)

    if not db_places:
        return NearbySearchResponse(places=[], region_status=status, region_id=region_id)

    # Batch-fetch top mention snippet per place (one query, not N)
    all_place_ids = [p["place_id"] for p in db_places]
    top_snippets = await supabase_client.get_top_snippets_for_places(all_place_ids)

    # Build Google data lookup for enrichment
    google_data_map: dict[str, dict] = {r["place_id"]: r for r in nearby_results}

    # Step 2: for DB places that also appeared in the nearby search, write
    # fresh Google data back to the DB (photos, rating, hours).
    # Writes run concurrently and are awaited before the response so data is
    # guaranteed persisted — no fire-and-forget background tasks for this step.
    now = datetime.now(timezone.utc).isoformat()
    pending_writes: list[tuple[str, dict]] = []
    for place_row in db_places:
        pid = place_row["place_id"]
        gdata = google_data_map.get(pid)
        if not gdata:
            continue  # outside nearby radius — keep cached values

        db_update: dict = {"last_enriched_at": now}
        if gdata.get("photo_urls"):
            db_update["photos"] = gdata["photo_urls"]
        if gdata.get("primary_type") is not None:
            db_update["primary_type"] = gdata["primary_type"]
        if gdata.get("rating") is not None:
            db_update["rating"] = gdata["rating"]
        if gdata.get("user_rating_count") is not None:
            db_update["user_rating_count"] = gdata["user_rating_count"]
        if gdata.get("regular_opening_hours") is not None:
            db_update["regular_opening_hours"] = gdata["regular_opening_hours"]

        pending_writes.append((pid, db_update))

    if pending_writes:
        await asyncio.gather(*[
            supabase_client.save_google_place_data(pid, update)
            for pid, update in pending_writes
        ])
        logger.info("nearby-search: %d places enriched from Google data", len(pending_writes))

    # Step 3: build response — live Google data takes precedence over cached DB values
    response_places: list[PlacePinResponse] = []
    for place_row in db_places:
        pid = place_row["place_id"]
        gdata = google_data_map.get(pid, {})

        response_places.append(
            PlacePinResponse(
                place_id=pid,
                name=place_row["name"],
                address=place_row.get("address"),
                lat=place_row["lat"],
                lng=place_row["lng"],
                wfh_score=place_row.get("wfh_score") or 0.0,
                has_wifi=place_row.get("has_wifi"),
                has_outlets=place_row.get("has_outlets"),
                is_laptop_friendly=place_row.get("is_laptop_friendly"),
                noise_level=place_row.get("noise_level"),
                seating_comfort=place_row.get("seating_comfort"),
                mention_count=place_row.get("mention_count") or 0,
                source_count=place_row.get("source_count") or 0,
                photos=gdata.get("photo_urls") or place_row.get("photos") or [],
                primary_type=gdata.get("primary_type") or place_row.get("primary_type"),
                rating=(
                    gdata.get("rating")
                    if gdata.get("rating") is not None
                    else place_row.get("rating")
                ),
                user_rating_count=(
                    gdata.get("user_rating_count")
                    if gdata.get("user_rating_count") is not None
                    else place_row.get("user_rating_count")
                ),
                regular_opening_hours=(
                    gdata.get("regular_opening_hours")
                    or place_row.get("regular_opening_hours")
                ),
                top_mention_snippet=top_snippets.get(pid),
            )
        )

    logger.info("nearby-search: returning %d pins (%d enriched from Google)", len(response_places), enriched)

    return NearbySearchResponse(
        places=response_places,
        region_status=status,
        region_id=region_id,
    )
