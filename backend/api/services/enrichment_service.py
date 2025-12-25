"""
Enrichment service for orchestrating sync and async enrichment.
"""
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import BackgroundTasks

from backend.enrichment.types import Config
from backend.enrichment.places_manager import (
    process_nearby_search_sync,
    process_enrichment_async,
)
from backend.enrichment.json_storage import load_places_json, upsert_place_ids
from backend.api.services.json_service import DEFAULT_JSON_PATH

logger = logging.getLogger(__name__)

# Track enrichment status in memory
_enrichment_status: Dict[str, Dict[str, bool]] = {}


def get_enrichment_tracking() -> Dict[str, Dict[str, bool]]:
    """Get the in-memory enrichment status tracking."""
    return _enrichment_status


def set_enriching(place_id: str, enriching: bool):
    """Set enrichment status for a place_id."""
    if place_id not in _enrichment_status:
        _enrichment_status[place_id] = {}
    _enrichment_status[place_id]["enriching"] = enriching


def is_enriching(place_id: str) -> bool:
    """Check if a place is currently being enriched."""
    return _enrichment_status.get(place_id, {}).get("enriching", False)


def process_places_sync(
    cfg: Config,
    place_ids: List[str],
    nearby_results: Optional[List[Dict]] = None,
    json_path: str = DEFAULT_JSON_PATH,
) -> List[str]:
    """
    Process places with sync enrichment (place details).
    Uses locks to prevent duplicate processing.
    
    Args:
        cfg: Config object
        place_ids: List of place_ids to process
        nearby_results: Optional nearby_search results for binary attributes
        json_path: Path to JSON file
        
    Returns:
        List of processed place_ids
    """
    from backend.enrichment.process_lock import is_processing, TooManyErrorsError
    
    # Create mapping of place_id to nearby_result if provided
    nearby_result_map = {}
    if nearby_results:
        for result in nearby_results:
            place_id = result.get("id")
            if place_id:
                nearby_result_map[place_id] = result
    
    # Load places FIRST to verify file is readable and has data
    places_before = load_places_json(json_path)
    initial_count = len(places_before)
    logger.info(f"Loaded {initial_count} places from JSON before upsert")
    
    # Safety check: if file has data but we loaded 0, something is wrong
    import os
    if initial_count == 0 and os.path.exists(json_path) and os.path.getsize(json_path) > 1000:
        logger.error(f"CRITICAL: JSON file has {os.path.getsize(json_path)} bytes but loaded 0 places. Aborting to prevent data loss.")
        raise ValueError(f"JSON file appears corrupted - loaded 0 places from {os.path.getsize(json_path)} byte file. Aborting upsert to prevent data loss.")
    
    # Upsert place_ids that don't exist (atomic operation)
    upsert_place_ids(json_path, place_ids)
    
    # Reload after upsert and verify we didn't lose data
    places = load_places_json(json_path)
    final_count = len(places)
    logger.info(f"Loaded {final_count} places from JSON after upsert")
    
    # Safety check: if we had data before and now have less, something went wrong
    if initial_count > 0 and final_count < initial_count:
        logger.error(f"CRITICAL: Data loss detected! Had {initial_count} places, now have {final_count}. This should not happen.")
        raise ValueError(f"Data loss detected during upsert: {initial_count} -> {final_count} places")
    
    # Process each place that needs sync enrichment
    processed = []
    for place_id in place_ids:
        if place_id not in places:
            logger.warning(f"Place {place_id} not found after upsert, skipping")
            continue
        
        place = places[place_id]
        
        # Check if already enriched
        if place.get("places_details_flag", False):
            processed.append(place_id)
            continue
        
        # Check if already being processed
        if is_processing(place_id):
            logger.debug(f"Place {place_id} is already being processed, skipping")
            continue
        
        # Need sync enrichment
        nearby_result = nearby_result_map.get(place_id)
        try:
            from backend.enrichment.place_enrichment import enrich_place_details_sync
            from backend.enrichment.json_storage import upsert_place
            
            # Reload place data before processing (might have been updated)
            places = load_places_json(json_path)
            if place_id not in places:
                continue
            place = places[place_id]
            
            # Double-check flag after reload
            if place.get("places_details_flag", False):
                processed.append(place_id)
                continue
            
            updated_place = enrich_place_details_sync(cfg, place_id, place, nearby_result)
            upsert_place(json_path, updated_place)
            processed.append(place_id)
            logger.info(f"Sync enrichment completed for {place_id}")
        except TooManyErrorsError:
            logger.error(f"Place {place_id} has too many errors, skipping")
            processed.append(place_id)  # Mark as processed to avoid retrying
        except Exception as e:
            logger.error(f"Sync enrichment failed for {place_id}: {e}", exc_info=True)
            # Don't mark as processed on error, allow retry
    
    return processed


def process_places_async_background(
    cfg: Config,
    place_ids: List[str],
    json_path: str = DEFAULT_JSON_PATH,
):
    """
    Background task for async enrichment.
    
    Args:
        cfg: Config object
        place_ids: List of place_ids to enrich
        json_path: Path to JSON file
    """
    for place_id in place_ids:
        set_enriching(place_id, True)
    
    try:
        count = process_enrichment_async(cfg, place_ids, json_path)
        logger.info(f"Async enrichment completed for {count} places")
    except Exception as e:
        logger.error(f"Async enrichment failed: {e}")
    finally:
        for place_id in place_ids:
            set_enriching(place_id, False)


def process_places_async(
    background_tasks: BackgroundTasks,
    cfg: Config,
    place_ids: List[str],
    json_path: str = DEFAULT_JSON_PATH,
):
    """
    Trigger async enrichment in background.
    Uses locks to prevent duplicate processing.
    
    Args:
        background_tasks: FastAPI BackgroundTasks
        cfg: Config object
        place_ids: List of place_ids to enrich
        json_path: Path to JSON file
    """
    from backend.enrichment.process_lock import is_processing
    
    # Filter to only places that need async enrichment and deduplicate
    places = load_places_json(json_path)
    place_ids_to_enrich = list(dict.fromkeys([  # Deduplicate while preserving order
        pid for pid in place_ids
        if pid in places 
        and not places[pid].get("enriched_flag", False) 
        and not is_enriching(pid)
        and not is_processing(pid)  # Also check process lock
    ]))
    
    if place_ids_to_enrich:
        for place_id in place_ids_to_enrich:
            set_enriching(place_id, True)
        
        background_tasks.add_task(
            process_places_async_background,
            cfg,
            place_ids_to_enrich,
            json_path,
        )
        logger.info(f"Scheduled async enrichment for {len(place_ids_to_enrich)} unique places")
    else:
        logger.info("No places need async enrichment (all already enriched or currently enriching)")
    
    return place_ids_to_enrich

