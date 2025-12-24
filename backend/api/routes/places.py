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
from backend.api.services.json_service import (
    get_places_data,
    get_enrichment_status,
    DEFAULT_JSON_PATH,
)
from backend.api.services.enrichment_service import (
    process_places_sync,
    process_places_async,
    get_enrichment_tracking,
    is_enriching,
)

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
        "library", "internet_cafe", "book_store",
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
        
        # Process sync enrichment (waits for completion)
        processed_place_ids = process_places_sync(
            cfg,
            place_ids,
            nearby_results=all_results,
            json_path=DEFAULT_JSON_PATH,
        )
        
        # Trigger async enrichment (background)
        async_place_ids = process_places_async(
            background_tasks,
            cfg,
            place_ids,
            json_path=DEFAULT_JSON_PATH,
        )
        
        # Get enriched data from JSON
        places_data = get_places_data(place_ids, json_path=DEFAULT_JSON_PATH)
        
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
                "places_details_flag": place_data.get("places_details_flag", False),
                "tavily_flag": place_data.get("tavily_flag", False),
                "enriched_flag": place_data.get("enriched_flag", False),
            }
            
            places_response.append(place_response)
            
            # Build enrichment status
            enrichment_status[place_id] = {
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
        
        places_data = get_places_data(place_id_list, json_path=DEFAULT_JSON_PATH)
        
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
        
        status = get_enrichment_status(place_id_list, json_path=DEFAULT_JSON_PATH)
        
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

