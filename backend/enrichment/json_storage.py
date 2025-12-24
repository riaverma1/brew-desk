"""
JSON file utilities for places bootstrap data.

JSON structure: Dictionary keyed by place_id
{
  "place_id_1": { "place_id": "place_id_1", "places_details_flag": false, ... },
  "place_id_2": { "place_id": "place_id_2", "places_details_flag": false, ... }
}
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def load_places_json(path: str) -> Dict[str, Dict]:
    """
    Load JSON file, return dictionary keyed by place_id.
    
    Args:
        path: Path to JSON file
        
    Returns:
        Dictionary keyed by place_id, or empty dict if file doesn't exist or is empty
    """
    logger.debug(f"[load_places_json] Attempting to load JSON from: {path}")
    logger.debug(f"[load_places_json] Absolute path: {os.path.abspath(path)}")
    
    if not os.path.exists(path):
        logger.info(f"[load_places_json] File does not exist: {path}")
        print(f"DEBUG: File does not exist: {path}")
        return {}
    
    file_size = os.path.getsize(path)
    logger.debug(f"[load_places_json] File size: {file_size} bytes")
    print(f"DEBUG: File exists, size: {file_size} bytes")
    
    # Check if file is empty
    if file_size == 0:
        logger.info(f"[load_places_json] File is empty: {path}")
        print(f"DEBUG: File is empty, returning empty dict")
        return {}
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            logger.debug(f"[load_places_json] File content length: {len(content)} chars")
            print(f"DEBUG: Read {len(content)} characters from file")
            if len(content) < 200:
                print(f"DEBUG: File content preview: {repr(content[:200])}")
            
            data = json.loads(content)
            logger.debug(f"[load_places_json] Successfully parsed JSON, type: {type(data)}")
            print(f"DEBUG: Parsed JSON successfully, type: {type(data)}")
            
    except (json.JSONDecodeError, ValueError) as e:
        # If JSON is invalid or empty, return empty dict
        logger.error(f"[load_places_json] JSON decode error: {e}")
        print(f"DEBUG: JSON decode error: {e}")
        return {}
    
    # Ensure it's a dictionary keyed by place_id
    if isinstance(data, dict):
        place_count = len(data)
        logger.info(f"[load_places_json] Loaded {place_count} places from JSON")
        print(f"DEBUG: Loaded {place_count} places from JSON")
        if place_count > 0:
            sample_ids = list(data.keys())[:3]
            print(f"DEBUG: Sample place_ids: {sample_ids}")
        return data
    elif isinstance(data, list):
        # Convert old array format to dict format
        logger.info(f"[load_places_json] Converting list format to dict format ({len(data)} items)")
        print(f"DEBUG: Converting list format to dict format ({len(data)} items)")
        result = {}
        for place in data:
            place_id = place.get("place_id")
            if place_id:
                result[place_id] = place
        logger.info(f"[load_places_json] Converted to {len(result)} places")
        print(f"DEBUG: Converted to {len(result)} places")
        return result
    else:
        logger.warning(f"[load_places_json] Unexpected data type: {type(data)}")
        print(f"DEBUG: Unexpected data type: {type(data)}, returning empty dict")
        return {}


def save_places_json(path: str, places: Dict[str, Dict]) -> None:
    """
    Save dictionary to JSON file.
    
    Args:
        path: Path to JSON file
        places: Dictionary keyed by place_id
    """
    logger.debug(f"[save_places_json] Saving to: {path}")
    logger.debug(f"[save_places_json] Absolute path: {os.path.abspath(path)}")
    place_count = len(places)
    logger.info(f"[save_places_json] Saving {place_count} places to JSON")
    print(f"DEBUG: Saving {place_count} places to JSON file: {path}")
    
    if place_count > 0:
        sample_ids = list(places.keys())[:3]
        print(f"DEBUG: Sample place_ids being saved: {sample_ids}")
        # Show structure of first place
        first_id = sample_ids[0]
        first_place = places[first_id]
        print(f"DEBUG: First place structure keys: {list(first_place.keys())}")
        print(f"DEBUG: First place flags - places_details: {first_place.get('places_details_flag')}, enriched: {first_place.get('enriched_flag')}")
    
    # Ensure directory exists
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
        logger.debug(f"[save_places_json] Created directory: {dir_path}")
    
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(places, f, ensure_ascii=False, indent=2)
        
        # Verify file was written
        if os.path.exists(path):
            saved_size = os.path.getsize(path)
            logger.info(f"[save_places_json] Successfully saved {saved_size} bytes")
            print(f"DEBUG: Successfully saved {saved_size} bytes to file")
        else:
            logger.error(f"[save_places_json] File was not created after write!")
            print(f"DEBUG: ERROR - File was not created after write!")
    except Exception as e:
        logger.error(f"[save_places_json] Error saving JSON: {e}")
        print(f"DEBUG: ERROR saving JSON: {e}")
        raise


def upsert_place(path: str, place: Dict) -> None:
    """
    Upsert a single place entry (add if new, update if exists) based on place_id.
    
    Args:
        path: Path to JSON file
        place: Place dictionary (must have "place_id" key)
    """
    place_id = place.get("place_id")
    if not place_id:
        raise ValueError("place must have 'place_id' key")
    
    logger.debug(f"[upsert_place] Upserting place: {place_id}")
    print(f"DEBUG: [upsert_place] Upserting place: {place_id}")
    
    places = load_places_json(path)
    was_existing = place_id in places
    logger.debug(f"[upsert_place] Place {'already exists' if was_existing else 'is new'}")
    print(f"DEBUG: [upsert_place] Place {'already exists' if was_existing else 'is new'}")
    
    places[place_id] = place
    save_places_json(path, places)
    
    logger.debug(f"[upsert_place] Successfully upserted: {place_id}")
    print(f"DEBUG: [upsert_place] Successfully upserted: {place_id}")


def upsert_place_ids(path: str, place_ids: List[str]) -> List[str]:
    """
    Upsert multiple place_ids, creating minimal entries for new ones.
    
    Args:
        path: Path to JSON file
        place_ids: List of place_ids to upsert
        
    Returns:
        List of place_ids that were newly created (not already in JSON)
    """
    logger.info(f"[upsert_place_ids] Starting upsert for {len(place_ids)} place_ids")
    print(f"DEBUG: [upsert_place_ids] Starting upsert for {len(place_ids)} place_ids")
    print(f"DEBUG: [upsert_place_ids] Place IDs to upsert: {place_ids}")
    
    places = load_places_json(path)
    logger.debug(f"[upsert_place_ids] Loaded {len(places)} existing places from JSON")
    print(f"DEBUG: [upsert_place_ids] Loaded {len(places)} existing places from JSON")
    
    if len(places) > 0:
        existing_ids = list(places.keys())[:5]
        print(f"DEBUG: [upsert_place_ids] Sample existing place_ids: {existing_ids}")
    
    new_place_ids = []
    existing_place_ids = []
    
    for place_id in place_ids:
        if place_id not in places:
            # Create minimal entry
            logger.debug(f"[upsert_place_ids] Creating new entry for: {place_id}")
            print(f"DEBUG: [upsert_place_ids] Creating NEW entry for: {place_id}")
            places[place_id] = {
                "place_id": place_id,
                "places_details_flag": False,
                "enriched_flag": False,
                "place": {},
                "sources": {},
                "derived": {}
            }
            new_place_ids.append(place_id)
        else:
            existing_place_ids.append(place_id)
            logger.debug(f"[upsert_place_ids] Place already exists: {place_id}")
            print(f"DEBUG: [upsert_place_ids] Place already EXISTS: {place_id}")
    
    logger.info(f"[upsert_place_ids] Created {len(new_place_ids)} new entries, {len(existing_place_ids)} already existed")
    print(f"DEBUG: [upsert_place_ids] Summary - New: {len(new_place_ids)}, Existing: {len(existing_place_ids)}")
    print(f"DEBUG: [upsert_place_ids] New place_ids: {new_place_ids}")
    
    logger.debug(f"[upsert_place_ids] Total places before save: {len(places)}")
    print(f"DEBUG: [upsert_place_ids] Total places before save: {len(places)}")
    
    save_places_json(path, places)
    
    # Verify after save
    verify_places = load_places_json(path)
    logger.debug(f"[upsert_place_ids] Verified after save: {len(verify_places)} places in file")
    print(f"DEBUG: [upsert_place_ids] Verified after save: {len(verify_places)} places in file")
    
    return new_place_ids


def reset_enrichment_flag(
    json_path: str,
    place_ids: Optional[List[str]] = None,
    clear_enrichment_data: bool = False
) -> int:
    """
    Reset enriched_flag to False for specified places (or all places) so enrichment can be rerun.
    
    This is useful when you want to rerun enrichment with updated code (e.g., improved Tavily queries).
    
    Args:
        json_path: Path to JSON file
        place_ids: Optional list of place_ids to reset. If None, resets all places.
        clear_enrichment_data: If True, also clears tavily data and derived attributes.
                              If False, keeps existing data for reference (default).
        
    Returns:
        Number of places that were reset
        
    Example:
        # Reset all places
        reset_enrichment_flag("backend/data/places_bootstrap.json")
        
        # Reset specific places
        reset_enrichment_flag("backend/data/places_bootstrap.json", place_ids=["place1", "place2"])
        
        # Reset and clear enrichment data
        reset_enrichment_flag("backend/data/places_bootstrap.json", clear_enrichment_data=True)
    """
    places = load_places_json(json_path)
    
    if not places:
        logger.info("[reset_enrichment_flag] No places found in JSON file")
        return 0
    
    # Determine which places to reset
    if place_ids is None:
        # Reset all places
        place_ids_to_reset = list(places.keys())
        logger.info(f"[reset_enrichment_flag] Resetting enrichment flag for all {len(place_ids_to_reset)} places")
    else:
        # Reset only specified places
        place_ids_to_reset = [pid for pid in place_ids if pid in places]
        not_found = set(place_ids) - set(place_ids_to_reset)
        if not_found:
            logger.warning(f"[reset_enrichment_flag] Place IDs not found: {not_found}")
        logger.info(f"[reset_enrichment_flag] Resetting enrichment flag for {len(place_ids_to_reset)} places")
    
    reset_count = 0
    for place_id in place_ids_to_reset:
        place = places[place_id]
        was_enriched = place.get("enriched_flag", False)
        
        if was_enriched or clear_enrichment_data:
            place["enriched_flag"] = False
            
            if clear_enrichment_data:
                # Clear enrichment-related data
                if "sources" in place and "tavily" in place["sources"]:
                    place["sources"]["tavily"] = {}
                if "derived" in place:
                    place["derived"] = {}
                if "enriched_at" in place:
                    del place["enriched_at"]
                if "enriched_version" in place:
                    del place["enriched_version"]
                logger.debug(f"[reset_enrichment_flag] Cleared enrichment data for {place_id}")
            
            reset_count += 1
    
    if reset_count > 0:
        save_places_json(json_path, places)
        logger.info(f"[reset_enrichment_flag] Successfully reset {reset_count} places")
    else:
        logger.info(f"[reset_enrichment_flag] No places needed resetting")
    
    return reset_count

