"""
POST /places/nearby-search — hot-path endpoint for all map pan events.

Steps:
  1. asyncio.gather: Google Nearby Search + region detection in parallel
  2. filter_eligible_places with thresholds from settings
  3. Merge photo_urls from nearby search into DB results; save new photos back (background)
  4. If cold region: background_tasks.add_task(trigger_seed) — non-blocking
  5. Return NearbySearchResponse immediately
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends

from config import Settings, get_settings
from models.place import NearbySearchRequest, NearbySearchResponse
from services import google_places, place_filter, region_detector, supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/places", tags=["places"])


@router.post("/nearby-search", response_model=NearbySearchResponse)
async def nearby_search(
    req: NearbySearchRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> NearbySearchResponse:
    # Step 1: parallel — Google Nearby Search + region detection
    nearby_results, (region_id, status) = await asyncio.gather(
        google_places.nearby_search_parallel(
            req.lat,
            req.lng,
            settings.nearby_search_radius_meters,
            settings.google_places_api_key,
        ),
        region_detector.detect_region_for_viewport(req.bounds),
    )

    # Build Google data lookup: place_id → {photos, primary_type, rating, ...}
    google_data_map: dict[str, dict] = {r["place_id"]: r for r in nearby_results}
    place_ids = [r["place_id"] for r in nearby_results]

    # Step 2: filter to DB-matched eligible places
    places = await place_filter.filter_eligible_places(
        place_ids,
        settings.pin_score_threshold,
        settings.pin_laptop_confidence_threshold,
    )

    # Step 3: merge Google data into response; save to DB in background
    for place in places:
        gdata = google_data_map.get(place.place_id, {})
        if not gdata:
            continue

        # Merge into response (live data takes precedence over stale DB values)
        place.photos = gdata.get("photo_urls") or place.photos
        place.primary_type = gdata.get("primary_type") or place.primary_type
        place.rating = gdata.get("rating") if gdata.get("rating") is not None else place.rating
        place.user_rating_count = gdata.get("user_rating_count") if gdata.get("user_rating_count") is not None else place.user_rating_count
        place.regular_opening_hours = gdata.get("regular_opening_hours") or place.regular_opening_hours

        # Persist to DB in background — only non-None fields
        db_update: dict = {}
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
        if db_update:
            background_tasks.add_task(
                supabase_client.save_google_place_data, place.place_id, db_update
            )

    # Step 4: trigger seed job for cold regions (non-blocking)
    if status == "cold" and region_id:
        from background.seed_job import trigger_seed
        background_tasks.add_task(trigger_seed, region_id)

    return NearbySearchResponse(places=places, region_status=status, region_id=region_id)
