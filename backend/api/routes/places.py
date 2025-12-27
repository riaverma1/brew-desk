"""
Places API routes.
"""
import math
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from backend.enrichment.types import Config
from backend.enrichment.google_places import nearby_search
from backend.api.services.db_service import (
    get_places_data,
    get_enrichment_status,
)
from backend.api.services.enrichment_service import (
    process_places_sync,
    process_places_async,
    get_enrichment_tracking,
    is_enriching,
    set_enriching,
)
from backend.enrichment.places_manager import (
    save_basic_info_to_json,
    select_top_n_places,
)
from backend.enrichment.place_enrichment import (
    enrich_place_details_sync,
    enrich_place_web_async,
)
from backend.enrichment.db_storage import load_all_places, upsert_place

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/places", tags=["places"])


def get_places_api_key() -> str:
    """Get Google Places API key from environment."""
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_PLACES_API_KEY environment variable not set")
    return api_key


class NearbySearchRequest(BaseModel):
    lat: float
    lng: float
    radius: int = 1200
    types: List[str] = [
        "cafe", "coffee_shop", "bakery", "tea_house",
        "library", "internet_cafe",
    ]


@router.post("/nearby-search")
async def nearby_search_endpoint(
    request: NearbySearchRequest,
    background_tasks: BackgroundTasks,
):
    """
    Search for nearby places, trigger enrichment, and return enriched data.
    
    This is the main endpoint that:
    1. Calls Google Places Nearby Search
    2. Triggers sync enrichment (waits for completion)
    3. Triggers async enrichment (background)
    4. Returns places data with enrichment status
    """
    try:
        logger.info(f"Received nearby-search request: lat={request.lat}, lng={request.lng}, radius={request.radius}, types={len(request.types)}")
        
        # Create config for Google Places API
        api_key = get_places_api_key()
        cfg = Config(
            api_key=api_key,
            lat=request.lat,
            lng=request.lng,
            radius_m=request.radius,
            nearby_search_radius_m=request.radius,
            include_types=tuple(request.types),
        )
        
        # Call Google Places Nearby Search for each type
        all_results = []
        for place_type in request.types:
            try:
                logger.info(f"Searching for type: {place_type}")
                results = nearby_search(cfg, place_type)
                logger.info(f"Found {len(results)} results for type {place_type}")
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Failed to search for type {place_type}: {e}", exc_info=True)
                continue
        
        logger.info(f"Total results from Google Places API: {len(all_results)}")
        
        # Filter out places with 'magazine' in name (early filtering to avoid processing)
        filtered_results = []
        for result in all_results:
            display_name_obj = result.get("displayName", {})
            display_name = display_name_obj.get("text", "") if isinstance(display_name_obj, dict) else str(display_name_obj) if display_name_obj else ""
            if "magazine" in display_name.lower():
                logger.debug(f"Excluding place '{display_name}' from Google Places results (magazine in name)")
                continue
            filtered_results.append(result)
        
        all_results = filtered_results
        logger.info(f"Results after filtering magazines: {len(all_results)}")
        
        if not all_results:
            logger.warning("No results from Google Places API")
            return {
                "places": [],
                "enrichment_status": {},
            }
        
        # Calculate distance from user location for each place and sort by distance
        def calculate_distance(lat1, lng1, lat2, lng2):
            """Calculate distance in meters using Haversine formula."""
            R = 6371000  # Earth radius in meters
            d_lat = math.radians(lat2 - lat1)
            d_lng = math.radians(lng2 - lng1)
            a = (math.sin(d_lat / 2) ** 2 +
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                 math.sin(d_lng / 2) ** 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            return R * c
        
        # Add distance to each result and sort
        for result in all_results:
            location = result.get("location", {})
            place_lat = location.get("latitude")
            place_lng = location.get("longitude")
            if place_lat and place_lng:
                result["_distance"] = calculate_distance(request.lat, request.lng, place_lat, place_lng)
            else:
                result["_distance"] = float("inf")
        
        # Sort by distance and limit to 20 closest places
        all_results.sort(key=lambda x: x.get("_distance", float("inf")))
        all_results = all_results[:20]
        logger.info(f"Limited to {len(all_results)} closest places")
        
        # Extract place_ids and deduplicate
        place_ids = list(dict.fromkeys([r.get("id") for r in all_results if r.get("id")]))  # Deduplicate while preserving order
        logger.info(f"Extracted {len(place_ids)} unique place_ids (after deduplication)")
        
        if not place_ids:
            logger.warning("No place_ids extracted from results")
            return {
                "places": [],
                "enrichment_status": {},
            }
        
        # Save basic info immediately (synchronous, but fast)
        try:
            saved_place_ids = save_basic_info_to_json(
                all_results,
                api_key,
            )
            logger.info(f"Saved basic info for {len(saved_place_ids)} places")
        except Exception as e:
            logger.error(f"Error saving basic info: {e}", exc_info=True)
            # Continue anyway - we can still return the results
            saved_place_ids = []
        
        # Pre-select top-5 places for enrichment (before triggering background task)
        # This allows us to mark them as enriching in the response
        from backend.enrichment.db_storage import load_places
        places_data_temp = load_places(place_ids)
        top_n_place_ids = select_top_n_places(
            places_data_temp,
            place_ids,
            request.lat,
            request.lng,
            request.radius,
            n=5,
        )
        
        # Set enriching flag for top-5 places immediately (so frontend can start polling)
        for place_id in top_n_place_ids:
            set_enriching(place_id, True)
        logger.info(f"Marked {len(top_n_place_ids)} places as enriching: {top_n_place_ids}")
        
        # Trigger background task for scoring + top-5 enrichment
        # FastAPI's BackgroundTasks handles exceptions automatically, but we wrap it
        # to ensure errors are logged and don't crash the background task system
        def safe_background_task():
            try:
                score_and_enrich_top_n_background(
                    cfg,
                    all_results,
                    request.lat,
                    request.lng,
                    request.radius,
                )
            except Exception as e:
                # Log but don't re-raise - FastAPI will handle it
                logger.error(f"[safe_background_task] Background task error: {e}", exc_info=True)
        
        background_tasks.add_task(safe_background_task)
        logger.info("Triggered background task for scoring and top-5 enrichment")
        
        # Get basic data from database (immediately, no waiting for enrichment)
        places_data = get_places_data(place_ids)
        
        # Build response with places and enrichment status
        places_response = []
        enrichment_status = {}
        
        for place_id in place_ids:
            place_data = places_data.get(place_id, {})
            place_obj = place_data.get("place", {})
            
            # Skip places with 'magazine' in name
            if "magazine" in place_obj.get("name", "").lower():
                logger.debug(f"Excluding place {place_id} (magazine in name)")
                continue
            
            # Build place response
            place_response = {
                "id": place_id,
                "name": place_obj.get("name", "Unknown"),
                "lat": place_obj.get("lat"),
                "lng": place_obj.get("lng"),
                "address": place_obj.get("formatted_address"),
                "rating": place_obj.get("rating"),
                "userRatingCount": place_obj.get("user_ratings_total"),
                "types": place_obj.get("types", []),
                "website": place_obj.get("website"),
                "priceLevel": place_obj.get("price_level"),
                "businessStatus": place_obj.get("business_status"),
                "openingHours": place_obj.get("opening_hours"),
                # Place detail attributes
                "restroom": place_obj.get("restroom"),
                "servesCoffee": place_obj.get("servesCoffee") or place_obj.get("ServesCoffee"),
                "outdoorSeating": place_obj.get("outdoorSeating"),
                "goodForGroups": place_obj.get("goodForGroups"),
                "accessibilityOptions": place_obj.get("accessibilityOptions"),
                "parkingOptions": place_obj.get("parkingOptions"),
                # Photos
                "photos": place_obj.get("photos", []),
                # Derived attributes
                "derived": place_data.get("derived", {}),
                # Enrichment flags
                "nearby_search_flag": place_data.get("nearby_search_flag", False),
                "places_details_flag": place_data.get("places_details_flag", False),
                "tavily_flag": place_data.get("tavily_flag", False),
                "enriched_flag": place_data.get("enriched_flag", False),
            }
            
            places_response.append(place_response)
            
            # Build enrichment status
            enrichment_status[place_id] = {
                "nearby_search_flag": place_data.get("nearby_search_flag", False),
                "places_details_flag": place_data.get("places_details_flag", False),
                "tavily_flag": place_data.get("tavily_flag", False),
                "enriched_flag": place_data.get("enriched_flag", False),
                "enriching": is_enriching(place_id),
            }
        
        return {
            "places": places_response,
            "enrichment_status": enrichment_status,
        }
        
    except Exception as e:
        logger.error(f"Error in nearby-search endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def score_and_enrich_top_n_background(
    cfg: Config,
    nearby_results: List[Dict],
    user_lat: float,
    user_lng: float,
    max_radius_m: float,
):
    """
    Background task: Score all places, select top-5, and enrich them.
    
    For top-5 places:
    - Run place_details enrichment (async) - fetches reviews + binary attributes
    - Run Tavily enrichment (async)
    - Wait for both to complete before running LLM
    - Run LLM derivation on all available evidence
    - Handle partial evidence cases
    
    Args:
        cfg: Config object
        nearby_results: List of nearby_search result dictionaries
        user_lat: User's latitude
        user_lng: User's longitude
        max_radius_m: Maximum radius in meters
    """
    from backend.enrichment.db_storage import load_places, load_place
    
    logger.info(f"[score_and_enrich_top_n_background] Starting background enrichment task")
    
    try:
        # Extract place_ids from nearby_results
        place_ids = [r.get("id") for r in nearby_results if r.get("id")]
        place_ids = list(dict.fromkeys(place_ids))  # Deduplicate
        
        if not place_ids:
            logger.warning("[score_and_enrich_top_n_background] No place_ids found")
            return
        
        # Load places from database
        places = load_places(place_ids)
        
        # Select top-5 places based on scoring
        top_n_place_ids = select_top_n_places(
            places,
            place_ids,
            user_lat,
            user_lng,
            max_radius_m,
            n=5,
        )
        
        if not top_n_place_ids:
            logger.info("[score_and_enrich_top_n_background] No places selected for enrichment (all already enriched)")
            return
        
        logger.info(f"[score_and_enrich_top_n_background] Selected top-{len(top_n_place_ids)} places: {top_n_place_ids}")
        
        # Create mapping of place_id to nearby_result
        place_id_to_result = {r.get("id"): r for r in nearby_results if r.get("id")}
        
        # Enrich each top-n place
        for place_id in top_n_place_ids:
            try:
                # Reload place to get latest data
                existing_place = load_place(place_id)
                if not existing_place:
                    logger.warning(f"[score_and_enrich_top_n_background] Place {place_id} not found in database")
                    continue
                
                # Skip if already enriched
                if existing_place.get("enriched_flag", False):
                    logger.info(f"[score_and_enrich_top_n_background] Place {place_id} already enriched, skipping")
                    continue
                
                # Set enriching flag to true (for frontend polling)
                set_enriching(place_id, True)
                logger.info(f"[score_and_enrich_top_n_background] Set enriching flag for {place_id}")
                
                # Step 1: Run place_details enrichment (fetch reviews + binary attributes)
                logger.info(f"[score_and_enrich_top_n_background] Running place_details for {place_id}")
                nearby_result = place_id_to_result.get(place_id)
                
                try:
                    updated_place = enrich_place_details_sync(cfg, place_id, existing_place, nearby_result)
                    upsert_place(updated_place)
                    logger.info(f"[score_and_enrich_top_n_background] Completed place_details for {place_id}")
                except Exception as e:
                    logger.error(f"[score_and_enrich_top_n_background] place_details failed for {place_id}: {e}", exc_info=True)
                    # Continue to try Tavily even if place_details failed
                
                # Step 2: Run Tavily enrichment
                logger.info(f"[score_and_enrich_top_n_background] Running Tavily for {place_id}")
                
                # Reload to get updated place data
                existing_place = load_place(place_id)
                if not existing_place:
                    continue
                place_obj = existing_place.get("place", {})
                
                if not place_obj:
                    logger.warning(f"[score_and_enrich_top_n_background] Place {place_id} has no place object, skipping Tavily")
                    continue
                
                try:
                    updated_place = enrich_place_web_async(cfg, place_obj, existing_place)
                    upsert_place(updated_place)
                    logger.info(f"[score_and_enrich_top_n_background] Completed Tavily + LLM for {place_id}")
                except Exception as e:
                    logger.error(f"[score_and_enrich_top_n_background] Tavily/LLM failed for {place_id}: {e}", exc_info=True)
                    # Continue to next place
                
                # Clear enriching flag when done (success or failure)
                set_enriching(place_id, False)
                logger.info(f"[score_and_enrich_top_n_background] Cleared enriching flag for {place_id}")
                
            except Exception as e:
                logger.error(f"[score_and_enrich_top_n_background] Error enriching {place_id}: {e}", exc_info=True)
                # Clear enriching flag even on error
                set_enriching(place_id, False)
                continue
        
        logger.info(f"[score_and_enrich_top_n_background] Completed background enrichment task")
        
    except Exception as e:
        logger.error(f"[score_and_enrich_top_n_background] Background task failed: {e}", exc_info=True)
        # Re-raise to ensure proper cleanup, but don't let it propagate to FastAPI
        import traceback
        logger.error(f"[score_and_enrich_top_n_background] Traceback: {traceback.format_exc()}")


@router.post("/enrich/{place_id}")
async def enrich_place_endpoint(place_id: str):
    """
    Ad-hoc enrichment endpoint for user-triggered enrichment.
    
    Runs place_details enrichment (synchronous/immediate) - fetches reviews + binary attributes
    Runs Tavily enrichment (synchronous/immediate)
    Waits for both to complete before running LLM
    Runs LLM derivation on all available evidence
    Handles partial evidence cases (same logic as background task)
    
    Args:
        place_id: Place ID to enrich
        
    Returns:
        Updated place data
    """
    try:
        logger.info(f"Received enrich request for place_id: {place_id}")
        
        # Create config for Google Places API
        api_key = get_places_api_key()
        cfg = Config(
            api_key=api_key,
            lat=0.0,  # Not used for place_details
            lng=0.0,  # Not used for place_details
            radius_m=1200,
            nearby_search_radius_m=1200,
            include_types=tuple([]),
        )
        
        # Load place from database
        from backend.enrichment.db_storage import load_place
        existing_place = load_place(place_id)
        if not existing_place:
            raise HTTPException(status_code=404, detail=f"Place {place_id} not found")
        
        # Check if already enriched
        if existing_place.get("enriched_flag", False):
            logger.info(f"Place {place_id} already enriched, returning existing data")
            place_obj = existing_place.get("place", {})
            return {
                "id": place_id,
                "name": place_obj.get("name", "Unknown"),
                "lat": place_obj.get("lat"),
                "lng": place_obj.get("lng"),
                "address": place_obj.get("formatted_address"),
                "rating": place_obj.get("rating"),
                "userRatingCount": place_obj.get("user_ratings_total"),
                "types": place_obj.get("types", []),
                "website": place_obj.get("website"),
                "priceLevel": place_obj.get("price_level"),
                "businessStatus": place_obj.get("business_status"),
                "openingHours": place_obj.get("opening_hours"),
                "restroom": place_obj.get("restroom"),
                "servesCoffee": place_obj.get("servesCoffee") or place_obj.get("ServesCoffee"),
                "outdoorSeating": place_obj.get("outdoorSeating"),
                "goodForGroups": place_obj.get("goodForGroups"),
                "accessibilityOptions": place_obj.get("accessibilityOptions"),
                "parkingOptions": place_obj.get("parkingOptions"),
                "photos": place_obj.get("photos", []),
                "derived": existing_place.get("derived", {}),
                "places_details_flag": existing_place.get("places_details_flag", False),
                "tavily_flag": existing_place.get("tavily_flag", False),
                "enriched_flag": existing_place.get("enriched_flag", False),
            }
        
        # Step 1: Run place_details enrichment (synchronous/immediate)
        logger.info(f"Running place_details enrichment for {place_id}")
        try:
            updated_place = enrich_place_details_sync(cfg, place_id, existing_place, nearby_result=None)
            upsert_place(updated_place)
            logger.info(f"Completed place_details for {place_id}")
        except Exception as e:
            logger.error(f"place_details failed for {place_id}: {e}", exc_info=True)
            # Continue to try Tavily even if place_details failed
        
        # Step 2: Run Tavily enrichment (synchronous/immediate)
        logger.info(f"Running Tavily enrichment for {place_id}")
        
        # Reload to get updated place data
        existing_place = load_place(place_id)
        if not existing_place:
            raise HTTPException(status_code=404, detail=f"Place {place_id} not found after place_details")
        
        place_obj = existing_place.get("place", {})
        
        if not place_obj:
            raise HTTPException(status_code=500, detail=f"Place {place_id} has no place object")
        
        try:
            updated_place = enrich_place_web_async(cfg, place_obj, existing_place)
            upsert_place(updated_place)
            logger.info(f"Completed Tavily + LLM for {place_id}")
        except Exception as e:
            logger.error(f"Tavily/LLM failed for {place_id}: {e}", exc_info=True)
            # Return partial data if available
        
        # Reload final data
        final_place = load_place(place_id)
        if not final_place:
            raise HTTPException(status_code=404, detail=f"Place {place_id} not found after enrichment")
        
        final_place_obj = final_place.get("place", {})
        
        # Return updated place data
        return {
            "id": place_id,
            "name": final_place_obj.get("name", "Unknown"),
            "lat": final_place_obj.get("lat"),
            "lng": final_place_obj.get("lng"),
            "address": final_place_obj.get("formatted_address"),
            "rating": final_place_obj.get("rating"),
            "userRatingCount": final_place_obj.get("user_ratings_total"),
            "types": final_place_obj.get("types", []),
            "website": final_place_obj.get("website"),
            "priceLevel": final_place_obj.get("price_level"),
            "businessStatus": final_place_obj.get("business_status"),
            "openingHours": final_place_obj.get("opening_hours"),
            "restroom": final_place_obj.get("restroom"),
            "servesCoffee": final_place_obj.get("servesCoffee") or final_place_obj.get("ServesCoffee"),
            "outdoorSeating": final_place_obj.get("outdoorSeating"),
            "goodForGroups": final_place_obj.get("goodForGroups"),
            "accessibilityOptions": final_place_obj.get("accessibilityOptions"),
            "parkingOptions": final_place_obj.get("parkingOptions"),
            "photos": final_place_obj.get("photos", []),
            "derived": final_place.get("derived", {}),
            "places_details_flag": final_place.get("places_details_flag", False),
            "tavily_flag": final_place.get("tavily_flag", False),
            "enriched_flag": final_place.get("enriched_flag", False),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in enrich endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data")
async def get_places_data_endpoint(
    place_ids: str = Query(..., description="Comma-separated list of place_ids"),
):
    """
    Get enriched place data for given place_ids.
    
    Used by frontend to refresh data after async enrichment completes.
    """
    try:
        place_id_list = [pid.strip() for pid in place_ids.split(",") if pid.strip()]
        
        if not place_id_list:
            return {"places": []}
        
        places_data = get_places_data(place_id_list)
        
        places_response = []
        for place_id in place_id_list:
            place_data = places_data.get(place_id, {})
            place_obj = place_data.get("place", {})
            
            # Skip places with 'magazine' in name
            if "magazine" in place_obj.get("name", "").lower():
                logger.debug(f"Excluding place {place_id} (magazine in name)")
                continue
            
            place_response = {
                "id": place_id,
                "name": place_obj.get("name", "Unknown"),
                "lat": place_obj.get("lat"),
                "lng": place_obj.get("lng"),
                "address": place_obj.get("formatted_address"),
                "rating": place_obj.get("rating"),
                "userRatingCount": place_obj.get("user_ratings_total"),
                "types": place_obj.get("types", []),
                "website": place_obj.get("website"),
                "priceLevel": place_obj.get("price_level"),
                "businessStatus": place_obj.get("business_status"),
                "openingHours": place_obj.get("opening_hours"),
                # Place detail attributes
                "restroom": place_obj.get("restroom"),
                "servesCoffee": place_obj.get("servesCoffee") or place_obj.get("ServesCoffee"),
                "outdoorSeating": place_obj.get("outdoorSeating"),
                "goodForGroups": place_obj.get("goodForGroups"),
                "accessibilityOptions": place_obj.get("accessibilityOptions"),
                "parkingOptions": place_obj.get("parkingOptions"),
                # Photos
                "photos": place_obj.get("photos", []),
                # Derived attributes
                "derived": place_data.get("derived", {}),
                # Enrichment flags
                "places_details_flag": place_data.get("places_details_flag", False),
                "tavily_flag": place_data.get("tavily_flag", False),
                "enriched_flag": place_data.get("enriched_flag", False),
            }
            
            places_response.append(place_response)
        
        return {"places": places_response}
        
    except Exception as e:
        logger.error(f"Error in data endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_enrichment_status_endpoint(
    place_ids: str = Query(..., description="Comma-separated list of place_ids"),
):
    """
    Get enrichment status for given place_ids (read-only, for polling).
    
    Used by frontend to poll for async enrichment completion.
    """
    try:
        place_id_list = [pid.strip() for pid in place_ids.split(",") if pid.strip()]
        
        if not place_id_list:
            return {}
        
        status = get_enrichment_status(place_id_list)
        
        # Add enriching status from memory
        for place_id in place_id_list:
            if place_id in status:
                status[place_id]["enriching"] = is_enriching(place_id)
            else:
                status[place_id] = {
                    "places_details_flag": False,
                    "tavily_flag": False,
                    "enriched_flag": False,
                    "enriching": False,
                }
        
        return status
        
    except Exception as e:
        logger.error(f"Error in status endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

