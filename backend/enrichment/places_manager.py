"""
Orchestration module for sync and async place enrichment operations.
"""

import logging
import os
from typing import Dict, List, Optional

from backend.enrichment.types import Config
from backend.enrichment.json_storage import load_places_json, upsert_place, upsert_place_ids
from backend.enrichment.place_enrichment import enrich_place_details_sync, enrich_place_web_async

logger = logging.getLogger(__name__)

DEFAULT_JSON_PATH = "backend/data/places_bootstrap.json"


def process_nearby_search_sync(
    cfg: Config,
    results: List[Dict],
    json_path: str = DEFAULT_JSON_PATH,
) -> List[str]:
    """
    Process nearby_search results: upsert place_ids and optionally fetch place_details.
    
    This is a SYNC operation that happens during nearby_search.
    Does NOT call Tavily or async enrichment.
    
    Args:
        cfg: Config object
        results: List of nearby_search result dictionaries
        json_path: Path to JSON file
        
    Returns:
        List of place_ids that were processed
    """
    logger.info(f"[process_nearby_search_sync] Starting processing of {len(results)} nearby_search results")
    print(f"DEBUG: [process_nearby_search_sync] Starting processing of {len(results)} nearby_search results")
    print(f"DEBUG: [process_nearby_search_sync] JSON path: {json_path}")
    print(f"DEBUG: [process_nearby_search_sync] Absolute JSON path: {os.path.abspath(json_path)}")
    
    # Extract place_ids from results (new API uses "id" field)
    place_ids = []
    for i, result in enumerate(results):
        place_id = result.get("id")  # New API uses "id" instead of "place_id"
        display_name_obj = result.get("displayName", {})
        display_name = display_name_obj.get("text", "Unknown") if isinstance(display_name_obj, dict) else str(display_name_obj) if display_name_obj else "Unknown"
        if place_id:
            place_ids.append(place_id)
            logger.debug(f"[process_nearby_search_sync] Result {i+1}: {display_name} -> {place_id}")
            if i < 3:  # Print first 3
                print(f"DEBUG: [process_nearby_search_sync] Result {i+1}: {display_name} -> {place_id}")
        else:
            logger.warning(f"[process_nearby_search_sync] Result {i+1} has no id: {result.keys()}")
            print(f"DEBUG: [process_nearby_search_sync] WARNING: Result {i+1} has no id")
    
    if not place_ids:
        logger.warning("[process_nearby_search_sync] No place_ids found in nearby_search results")
        print(f"DEBUG: [process_nearby_search_sync] ERROR: No place_ids found in results!")
        return []
    
    logger.info(f"[process_nearby_search_sync] Extracted {len(place_ids)} place_ids")
    print(f"DEBUG: [process_nearby_search_sync] Extracted {len(place_ids)} place_ids: {place_ids[:5]}")
    
    # Check JSON file state before upsert
    places_before = load_places_json(json_path)
    logger.debug(f"[process_nearby_search_sync] Places in JSON before upsert: {len(places_before)}")
    print(f"DEBUG: [process_nearby_search_sync] Places in JSON BEFORE upsert: {len(places_before)}")
    
    # Upsert place_ids (creates minimal entries for new ones)
    logger.info(f"[process_nearby_search_sync] Calling upsert_place_ids...")
    print(f"DEBUG: [process_nearby_search_sync] Calling upsert_place_ids...")
    new_place_ids = upsert_place_ids(json_path, place_ids)
    
    if new_place_ids:
        logger.info(f"[process_nearby_search_sync] Created {len(new_place_ids)} new place entries")
        print(f"DEBUG: [process_nearby_search_sync] Created {len(new_place_ids)} new place entries: {new_place_ids}")
    else:
        logger.info(f"[process_nearby_search_sync] All {len(place_ids)} places already existed")
        print(f"DEBUG: [process_nearby_search_sync] All {len(place_ids)} places already existed")
    
    # Load all places after upsert
    logger.debug(f"[process_nearby_search_sync] Loading places after upsert...")
    print(f"DEBUG: [process_nearby_search_sync] Loading places after upsert...")
    places = load_places_json(json_path)
    logger.info(f"[process_nearby_search_sync] Places in JSON after upsert: {len(places)}")
    print(f"DEBUG: [process_nearby_search_sync] Places in JSON AFTER upsert: {len(places)}")
    
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
            print(f"DEBUG: [process_nearby_search_sync] Fetching place details for {place_id}...")
            try:
                # Pass nearby_search result to extract binary attributes from it
                updated_place = enrich_place_details_sync(cfg, place_id, existing_place, nearby_result)
                logger.debug(f"[process_nearby_search_sync] Successfully enriched {place_id}, upserting...")
                print(f"DEBUG: [process_nearby_search_sync] Successfully enriched {place_id}, upserting...")
                upsert_place(json_path, updated_place)
                logger.info(f"[process_nearby_search_sync] Enriched place details for {place_id}")
                print(f"DEBUG: [process_nearby_search_sync] ✓ Enriched place details for {place_id}")
            except Exception as e:
                logger.error(f"[process_nearby_search_sync] Failed to enrich place details for {place_id}: {e}")
                print(f"DEBUG: [process_nearby_search_sync] ERROR enriching {place_id}: {e}")
        else:
            logger.debug(f"[process_nearby_search_sync] Skipping {place_id} - already has details")
            print(f"DEBUG: [process_nearby_search_sync] Skipping {place_id} - already has details")
        
        processed.append(place_id)
    
    logger.info(f"[process_nearby_search_sync] Completed processing {len(processed)} places")
    print(f"DEBUG: [process_nearby_search_sync] Completed processing {len(processed)} places")
    
    # Final verification
    final_places = load_places_json(json_path)
    logger.info(f"[process_nearby_search_sync] Final places count in JSON: {len(final_places)}")
    print(f"DEBUG: [process_nearby_search_sync] Final places count in JSON: {len(final_places)}")
    
    return processed


def process_enrichment_async(
    cfg: Config,
    place_ids: Optional[List[str]] = None,
    json_path: str = DEFAULT_JSON_PATH,
) -> int:
    """
    Process async enrichment (Tavily + LLM) for places where enriched_flag is false.
    
    This is an ASYNC operation that should be called separately, not during nearby_search.
    
    Args:
        cfg: Config object
        place_ids: Optional list of place_ids to enrich. If None, processes all places needing enrichment.
        json_path: Path to JSON file
        
    Returns:
        Count of places enriched
    """
    places = load_places_json(json_path)
    
    # Determine which places to process
    if place_ids is None:
        # Process all places needing enrichment
        place_ids_to_process = [
            pid for pid, place in places.items()
            if not place.get("enriched_flag", False)
        ]
    else:
        # Process only specified place_ids that need enrichment
        place_ids_to_process = [
            pid for pid in place_ids
            if pid in places and not places[pid].get("enriched_flag", False)
        ]
    
    if not place_ids_to_process:
        logger.info("No places need async enrichment")
        return 0
    
    logger.info(f"Processing async enrichment for {len(place_ids_to_process)} places")
    
    enriched_count = 0
    for place_id in place_ids_to_process:
        existing_place = places[place_id]
        
        # Get place object for enrichment
        place_obj = existing_place.get("place", {})
        if not place_obj:
            logger.warning(f"Place {place_id} has no place object, skipping async enrichment")
            continue
        
        try:
            updated_place = enrich_place_web_async(cfg, place_obj, existing_place)
            upsert_place(json_path, updated_place)
            enriched_count += 1
            logger.info(f"Completed async enrichment for {place_id} ({enriched_count}/{len(place_ids_to_process)})")
        except Exception as e:
            logger.error(f"Failed async enrichment for {place_id}: {e}")
    
    return enriched_count


def get_places_needing_enrichment(json_path: str = DEFAULT_JSON_PATH) -> List[str]:
    """
    Get list of place_ids where enriched_flag is false.
    
    Args:
        json_path: Path to JSON file
        
    Returns:
        List of place_ids needing enrichment
    """
    places = load_places_json(json_path)
    return [
        pid for pid, place in places.items()
        if not place.get("enriched_flag", False)
    ]

