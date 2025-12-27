"""
Orchestration module for sync and async place enrichment operations.
"""

import logging
import os
import math
from typing import Dict, List, Optional

from backend.enrichment.types import Config
from backend.enrichment.db_storage import load_all_places, upsert_place, upsert_place_ids
from backend.enrichment.place_enrichment import enrich_place_details_sync, enrich_place_web_async
from backend.enrichment.google_places import process_photos


def _normalize_display_name(display_name) -> str:
    """
    Normalize displayName from new Places API to a string.
    
    Args:
        display_name: displayName field from API (can be dict with 'text' key or string)
        
    Returns:
        String representation of the display name
    """
    if isinstance(display_name, dict) and "text" in display_name:
        return display_name["text"]
    elif isinstance(display_name, str):
        return display_name
    return ""

logger = logging.getLogger(__name__)


def extract_basic_info_from_nearby_search(nearby_result: Dict, api_key: str) -> Dict:
    """
    Extract basic info from nearby_search result.
    
    Extracts ONLY: name, photos (processed), rating, user_ratings_total, types, 
    regular_opening_hours, price_level, website, neighborhood, business_status, 
    formatted_address, lat, lng.
    
    Does NOT include binary attributes (restroom, servesCoffee, etc.) - those come later from place_details.
    
    Args:
        nearby_result: Nearby search result dictionary from Google Places API
        api_key: Google Places API key for processing photos
        
    Returns:
        Place object dictionary with basic info
    """
    location_obj = nearby_result.get("location", {})
    display_name_obj = nearby_result.get("displayName", {})
    display_name_text = _normalize_display_name(display_name_obj)
    
    # Process photos (prefer interior, limit to 5)
    photos = nearby_result.get("photos", [])
    processed_photos = process_photos(photos, api_key, max_photos=5)
    
    # Extract neighborhood (simple implementation - returns None for now)
    neighborhood = None  # Could be enhanced later
    
    place_obj = {
        "name": display_name_text,
        "lat": location_obj.get("latitude"),
        "lng": location_obj.get("longitude"),
        "types": nearby_result.get("types", []),
        "formatted_address": nearby_result.get("formattedAddress", ""),
        "neighborhood": neighborhood,
        "website": nearby_result.get("websiteUri"),
        "rating": nearby_result.get("rating"),
        "user_ratings_total": nearby_result.get("userRatingCount"),
        "price_level": nearby_result.get("priceLevel"),
        "business_status": nearby_result.get("businessStatus"),
        "opening_hours": nearby_result.get("regularOpeningHours"),
        "photos": processed_photos,
    }
    
    return place_obj


def save_basic_info_to_json(
    nearby_results: List[Dict],
    api_key: str,
) -> List[str]:
    """
    Save basic info from nearby_search results to database immediately.
    
    For each nearby_result:
    - Extract basic info using extract_basic_info_from_nearby_search
    - Upsert place_id if needed
    - Update place object with basic info
    - Set nearby_search_flag = True
    - Set places_details_flag = False (not yet enriched)
    - Save to database
    
    Args:
        nearby_results: List of nearby_search result dictionaries
        api_key: Google Places API key for processing photos
        
    Returns:
        List of place_ids that were saved
    """
    from backend.enrichment.db_storage import load_places
    
    logger.info(f"[save_basic_info_to_json] Saving basic info for {len(nearby_results)} places")
    
    # Extract place_ids first
    place_ids = []
    place_id_to_result = {}
    for result in nearby_results:
        place_id = result.get("id")
        if place_id:
            place_ids.append(place_id)
            place_id_to_result[place_id] = result
    
    if not place_ids:
        logger.warning("[save_basic_info_to_json] No place_ids found in nearby_search results")
        return []
    
    # Upsert place_ids (creates minimal entries for new ones)
    upsert_place_ids(place_ids)
    
    # Load places after upsert
    places = load_places(place_ids)
    
    # Update each place with basic info
    saved_place_ids = []
    for place_id in place_ids:
        if place_id not in places:
            logger.warning(f"[save_basic_info_to_json] Place {place_id} not found after upsert")
            continue
        
        existing_place = places[place_id]
        nearby_result = place_id_to_result.get(place_id)
        
        if not nearby_result:
            logger.warning(f"[save_basic_info_to_json] No nearby_result for {place_id}")
            continue
        
        # Extract basic info (handle errors gracefully)
        try:
            basic_info = extract_basic_info_from_nearby_search(nearby_result, api_key)
        except Exception as e:
            logger.error(f"[save_basic_info_to_json] Failed to extract basic info for {place_id}: {e}", exc_info=True)
            # Continue with next place - don't fail the whole operation
            continue
        
        # Update place object (merge with existing if any)
        existing_place_obj = existing_place.get("place", {})
        existing_place_obj.update(basic_info)
        existing_place["place"] = existing_place_obj
        
        # Set flags
        existing_place["nearby_search_flag"] = True
        # Don't overwrite places_details_flag if it's already True
        if not existing_place.get("places_details_flag", False):
            existing_place["places_details_flag"] = False
        
        # Save to database (handle errors gracefully)
        try:
            upsert_place(existing_place)
            saved_place_ids.append(place_id)
        except Exception as e:
            logger.error(f"[save_basic_info_to_json] Failed to save {place_id}: {e}", exc_info=True)
            # Continue with next place - don't fail the whole operation
            continue
    
    logger.info(f"[save_basic_info_to_json] Saved basic info for {len(saved_place_ids)} places")
    return saved_place_ids


def select_top_n_places(
    places: Dict[str, Dict],
    place_ids: List[str],
    user_lat: float,
    user_lng: float,
    max_radius_m: float,
    n: int = 5,
) -> List[str]:
    """
    Select top-n places based on scoring.
    
    Scores all places, sorts by score descending, and returns top-n place_ids.
    Filters out places already enriched (enriched_flag = True).
    
    Args:
        places: Dictionary of all places keyed by place_id
        place_ids: List of place_ids to consider (from nearby_search)
        user_lat: User's latitude
        user_lng: User's longitude
        max_radius_m: Maximum radius in meters
        n: Number of top places to select (default 5)
        
    Returns:
        List of top-n place_ids
    """
    from backend.enrichment.top_n_scoring import score_place
    
    # Filter to only places that need enrichment
    candidates = []
    for place_id in place_ids:
        if place_id not in places:
            continue
        place = places[place_id]
        # Skip if already enriched
        if place.get("enriched_flag", False):
            continue
        candidates.append((place_id, place))
    
    if not candidates:
        logger.info("[select_top_n_places] No candidates found (all already enriched)")
        return []
    
    # Calculate max_reviews for normalization
    # Filter out None values and convert to int
    review_counts = []
    for c in candidates:
        place_obj = c[1].get("place", {})
        user_ratings = place_obj.get("user_ratings_total")
        # Handle None values - convert to 0
        if user_ratings is None:
            user_ratings = 0
        else:
            try:
                user_ratings = int(user_ratings)
            except (ValueError, TypeError):
                user_ratings = 0
        review_counts.append(user_ratings)
    
    max_reviews = max(review_counts) if review_counts else 1
    
    # Score all candidates
    scored = []
    for place_id, place in candidates:
        score = score_place(place, user_lat, user_lng, max_radius_m, max_reviews)
        scored.append((place_id, score))
    
    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    
    # Return top-n place_ids
    top_n = [place_id for place_id, _ in scored[:n]]
    logger.info(f"[select_top_n_places] Selected top-{len(top_n)} places from {len(candidates)} candidates")
    
    return top_n


def process_nearby_search_sync(
    cfg: Config,
    results: List[Dict],
) -> List[str]:
    """
    Process nearby_search results: upsert place_ids and optionally fetch place_details.
    
    This is a SYNC operation that happens during nearby_search.
    Does NOT call Tavily or async enrichment.
    
    Args:
        cfg: Config object
        results: List of nearby_search result dictionaries
        
    Returns:
        List of place_ids that were processed
    """
    from backend.enrichment.db_storage import load_places
    
    logger.info(f"[process_nearby_search_sync] Starting processing of {len(results)} nearby_search results")
    
    # Extract place_ids from results (new API uses "id" field)
    place_ids = []
    for i, result in enumerate(results):
        place_id = result.get("id")  # New API uses "id" instead of "place_id"
        display_name_obj = result.get("displayName", {})
        display_name = display_name_obj.get("text", "Unknown") if isinstance(display_name_obj, dict) else str(display_name_obj) if display_name_obj else "Unknown"
        if place_id:
            place_ids.append(place_id)
            logger.debug(f"[process_nearby_search_sync] Result {i+1}: {display_name} -> {place_id}")
        else:
            logger.warning(f"[process_nearby_search_sync] Result {i+1} has no id: {result.keys()}")
    
    if not place_ids:
        logger.warning("[process_nearby_search_sync] No place_ids found in nearby_search results")
        return []
    
    logger.info(f"[process_nearby_search_sync] Extracted {len(place_ids)} place_ids")
    
    # Upsert place_ids (creates minimal entries for new ones)
    logger.info(f"[process_nearby_search_sync] Calling upsert_place_ids...")
    new_place_ids = upsert_place_ids(place_ids)
    
    if new_place_ids:
        logger.info(f"[process_nearby_search_sync] Created {len(new_place_ids)} new place entries")
    else:
        logger.info(f"[process_nearby_search_sync] All {len(place_ids)} places already existed")
    
    # Load places after upsert
    logger.debug(f"[process_nearby_search_sync] Loading places after upsert...")
    places = load_places(place_ids)
    logger.info(f"[process_nearby_search_sync] Places in database after upsert: {len(places)}")
    
    # Create a mapping of place_id to nearby_search result for extracting binary attributes (new API uses "id")
    place_id_to_result = {result.get("id"): result for result in results if result.get("id")}
    logger.debug(f"[process_nearby_search_sync] Created mapping for {len(place_id_to_result)} places from nearby_search")
    print(f"DEBUG: [process_nearby_search_sync] Created mapping for {len(place_id_to_result)} places from nearby_search")
    
    # Process each place_id
    processed = []
    for i, place_id in enumerate(place_ids):
        logger.debug(f"[process_nearby_search_sync] Processing place {i+1}/{len(place_ids)}: {place_id}")
        print(f"DEBUG: [process_nearby_search_sync] Processing place {i+1}/{len(place_ids)}: {place_id}")
        
        if place_id not in places:
            logger.warning(f"[process_nearby_search_sync] Place {place_id} not found in JSON after upsert!")
            print(f"DEBUG: [process_nearby_search_sync] ERROR: Place {place_id} not found in JSON after upsert!")
            continue
        
        existing_place = places[place_id]
        places_details_flag = existing_place.get("places_details_flag", False)
        logger.debug(f"[process_nearby_search_sync] Place {place_id} - places_details_flag: {places_details_flag}")
        print(f"DEBUG: [process_nearby_search_sync] Place {place_id} - places_details_flag: {places_details_flag}")
        
        # Get nearby_search result for this place_id to extract binary attributes
        nearby_result = place_id_to_result.get(place_id, {})
        
        # If places_details_flag is false, fetch place details
        if not places_details_flag:
            logger.info(f"[process_nearby_search_sync] Fetching place details for {place_id}...")
            try:
                # Pass nearby_search result to extract binary attributes from it
                updated_place = enrich_place_details_sync(cfg, place_id, existing_place, nearby_result)
                logger.debug(f"[process_nearby_search_sync] Successfully enriched {place_id}, upserting...")
                upsert_place(updated_place)
                logger.info(f"[process_nearby_search_sync] Enriched place details for {place_id}")
            except Exception as e:
                logger.error(f"[process_nearby_search_sync] Failed to enrich place details for {place_id}: {e}", exc_info=True)
        else:
            logger.debug(f"[process_nearby_search_sync] Skipping {place_id} - already has details")
        
        processed.append(place_id)
    
    logger.info(f"[process_nearby_search_sync] Completed processing {len(processed)} places")
    
    return processed


def process_enrichment_async(
    cfg: Config,
    place_ids: Optional[List[str]] = None,
) -> int:
    """
    Process async enrichment (Tavily + LLM) for places where enriched_flag is false.
    
    This is an ASYNC operation that should be called separately, not during nearby_search.
    
    Args:
        cfg: Config object
        place_ids: Optional list of place_ids to enrich. If None, processes all places needing enrichment.
        
    Returns:
        Count of places enriched
    """
    from backend.enrichment.db_storage import load_places
    
    # Determine which places to process
    if place_ids is None:
        # Process all places needing enrichment
        places = load_all_places()
        place_ids_to_process = [
            pid for pid, place in places.items()
            if not place.get("enriched_flag", False)
        ]
    else:
        # Process only specified place_ids that need enrichment
        places = load_places(place_ids)
        place_ids_to_process = [
            pid for pid in place_ids
            if pid in places and not places[pid].get("enriched_flag", False)
        ]
    
    if not place_ids_to_process:
        logger.info("No places need async enrichment")
        return 0
    
    # Deduplicate place_ids_to_process
    place_ids_to_process = list(dict.fromkeys(place_ids_to_process))  # Preserves order while removing duplicates
    
    logger.info(f"Processing async enrichment for {len(place_ids_to_process)} places (after deduplication)")
    
    enriched_count = 0
    processed_place_ids = set()  # Track processed place_ids to avoid duplicates within the same batch
    
    for place_id in place_ids_to_process:
        # Skip if already processed in this batch
        if place_id in processed_place_ids:
            logger.warning(f"Place {place_id} already processed in this batch, skipping duplicate")
            continue
        
        # Reload place from database before each enrichment to avoid race conditions
        from backend.enrichment.db_storage import load_place
        existing_place = load_place(place_id)
        
        if not existing_place:
            logger.warning(f"Place {place_id} not found in database, skipping")
            processed_place_ids.add(place_id)
            continue
        
        # Double-check enriched_flag after reload (might have been enriched by another process)
        if existing_place.get("enriched_flag", False):
            logger.info(f"Place {place_id} already enriched (checked after reload), skipping")
            processed_place_ids.add(place_id)
            continue
        
        # Get place object for enrichment
        place_obj = existing_place.get("place", {})
        if not place_obj:
            logger.warning(f"Place {place_id} has no place object, skipping async enrichment")
            processed_place_ids.add(place_id)
            continue
        
        try:
            from backend.enrichment.process_lock import AlreadyProcessingError, TooManyErrorsError
            
            updated_place = enrich_place_web_async(cfg, place_obj, existing_place)
            
            # Verify place_id is present before upserting
            if "place_id" not in updated_place:
                logger.error(f"Place {place_id} missing place_id in updated_place dict, cannot upsert")
                processed_place_ids.add(place_id)
                continue
            
            # Verify enriched_flag was set
            if not updated_place.get("enriched_flag", False):
                logger.warning(f"Place {place_id} enriched but enriched_flag not set to True")
            
            upsert_place(updated_place)
            
            # Verify the save worked by checking the database
            place_after = load_place(place_id)
            if place_after and place_after.get("enriched_flag", False):
                enriched_count += 1
                processed_place_ids.add(place_id)
                logger.info(f"Completed async enrichment for {place_id} ({enriched_count}/{len(place_ids_to_process)}) - verified in database")
            else:
                logger.error(f"Place {place_id} enriched but enriched_flag not found in database after upsert!")
                processed_place_ids.add(place_id)
        except AlreadyProcessingError:
            logger.warning(f"Place {place_id} is already being processed, skipping")
            processed_place_ids.add(place_id)
        except TooManyErrorsError:
            logger.error(f"Place {place_id} has too many errors, stopping processing")
            processed_place_ids.add(place_id)
        except Exception as e:
            logger.error(f"Failed async enrichment for {place_id}: {e}", exc_info=True)
            processed_place_ids.add(place_id)
    
    return enriched_count


def get_places_needing_enrichment() -> List[str]:
    """
    Get list of place_ids where enriched_flag is false.
    
    Returns:
        List of place_ids needing enrichment
    """
    places = load_all_places()
    return [
        pid for pid, place in places.items()
        if not place.get("enriched_flag", False)
    ]

