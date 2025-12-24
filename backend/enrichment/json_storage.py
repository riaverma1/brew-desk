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
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from backend.enrichment.file_lock import file_lock

logger = logging.getLogger(__name__)


def load_places_json(path: str, use_lock: bool = True) -> Dict[str, Dict]:
    """
    Load JSON file, return dictionary keyed by place_id.
    
    Args:
        path: Path to JSON file
        use_lock: Whether to use file locking (default True for thread safety)
        
    Returns:
        Dictionary keyed by place_id, or empty dict if file doesn't exist or is empty
    """
    logger.debug(f"[load_places_json] Attempting to load JSON from: {path}")
    logger.debug(f"[load_places_json] Absolute path: {os.path.abspath(path)}")
    
    if not os.path.exists(path):
        logger.info(f"[load_places_json] File does not exist: {path}")
        return {}
    
    file_size = os.path.getsize(path)
    logger.debug(f"[load_places_json] File size: {file_size} bytes")
    
    # Check if file is empty
    if file_size == 0:
        logger.info(f"[load_places_json] File is empty: {path}")
        return {}
    
    def _load():
        max_retries = 3
        data = {}
        for attempt in range(max_retries):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    logger.debug(f"[load_places_json] File content length: {len(content)} chars")
                    
                    data = json.loads(content)
                    logger.debug(f"[load_places_json] Successfully parsed JSON, type: {type(data)}")
                    break  # Success, exit retry loop
                    
            except (json.JSONDecodeError, ValueError) as e:
                if attempt < max_retries - 1:
                    # Retry reading (file might be mid-write)
                    logger.warning(f"[load_places_json] JSON decode error on attempt {attempt + 1}: {e}, retrying...")
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                else:
                    # Final attempt failed - create backup and try to recover
                    logger.error(f"[load_places_json] JSON decode error after {max_retries} attempts: {e}")
                    
                    # Create backup of corrupted file before returning empty
                    backup_path = path + ".corrupted_backup"
                    try:
                        if os.path.exists(path):
                            shutil.copy2(path, backup_path)
                            logger.warning(f"[load_places_json] Created backup of corrupted file: {backup_path}")
                    except Exception as backup_error:
                        logger.error(f"[load_places_json] Failed to create backup: {backup_error}")
                    
                    return {}
        
        # Ensure it's a dictionary keyed by place_id
        if isinstance(data, dict):
            place_count = len(data)
            logger.info(f"[load_places_json] Loaded {place_count} places from JSON")
            return data
        elif isinstance(data, list):
            # Convert old array format to dict format
            logger.info(f"[load_places_json] Converting list format to dict format ({len(data)} items)")
            result = {}
            for place in data:
                place_id = place.get("place_id")
                if place_id:
                    result[place_id] = place
            logger.info(f"[load_places_json] Converted to {len(result)} places")
            return result
        else:
            logger.warning(f"[load_places_json] Unexpected data type: {type(data)}")
            return {}
    
    if use_lock:
        try:
            with file_lock(path, timeout=5.0):
                return _load()
        except TimeoutError:
            logger.error(f"[load_places_json] Timeout acquiring lock for {path}")
            # Fallback to non-locked read if lock times out
            return _load()
    else:
        return _load()


def save_places_json(path: str, places: Dict[str, Dict], use_lock: bool = True) -> None:
    """
    Save dictionary to JSON file with atomic write and file locking.
    
    Args:
        path: Path to JSON file
        places: Dictionary keyed by place_id
        use_lock: Whether to use file locking (default True for thread safety)
    """
    logger.debug(f"[save_places_json] Saving to: {path}")
    logger.debug(f"[save_places_json] Absolute path: {os.path.abspath(path)}")
    place_count = len(places)
    logger.info(f"[save_places_json] Saving {place_count} places to JSON")
    
    # Ensure directory exists
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
        logger.debug(f"[save_places_json] Created directory: {dir_path}")
    
    def _save():
        # Use atomic write: write to temp file, then rename (atomic on most filesystems)
        temp_path = path + ".tmp"
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Write to temporary file first
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(places, f, ensure_ascii=False, indent=2)
                
                # Verify temp file was written correctly
                if not os.path.exists(temp_path):
                    raise IOError(f"Temp file was not created: {temp_path}")
                
                # Verify temp file is valid JSON
                with open(temp_path, "r", encoding="utf-8") as f:
                    json.load(f)  # Validate JSON
                
                # Atomic rename (replaces existing file atomically on most filesystems)
                shutil.move(temp_path, path)
                
                # Verify final file was written
                if os.path.exists(path):
                    saved_size = os.path.getsize(path)
                    logger.info(f"[save_places_json] Successfully saved {saved_size} bytes")
                    return  # Success, exit retry loop
                else:
                    raise IOError(f"File was not created after atomic rename: {path}")
                    
            except (json.JSONEncodeError, IOError, OSError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"[save_places_json] Error on attempt {attempt + 1}: {e}, retrying...")
                    # Clean up temp file if it exists
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                else:
                    # Final attempt failed
                    logger.error(f"[save_places_json] Error saving JSON after {max_retries} attempts: {e}")
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    raise
    
    if use_lock:
        try:
            with file_lock(path, timeout=10.0):
                _save()
        except TimeoutError:
            logger.error(f"[save_places_json] Timeout acquiring lock for {path}")
            raise IOError(f"Could not acquire lock to save {path}")
    else:
        _save()


def upsert_place(path: str, place: Dict) -> None:
    """
    Upsert a single place entry (add if new, update if exists) based on place_id.
    
    Uses file locking to handle concurrent writes atomically.
    
    Args:
        path: Path to JSON file
        place: Place dictionary (must have "place_id" key)
    """
    place_id = place.get("place_id")
    if not place_id:
        raise ValueError("place must have 'place_id' key")
    
    logger.debug(f"[upsert_place] Upserting place: {place_id}")
    
    try:
        with file_lock(path, timeout=10.0):
            places = load_places_json(path, use_lock=False)  # Already locked, don't lock again
            was_existing = place_id in places
            logger.debug(f"[upsert_place] Place {'already exists' if was_existing else 'is new'}")
            
            places[place_id] = place
            save_places_json(path, places, use_lock=False)  # Already locked, don't lock again
            
            logger.debug(f"[upsert_place] Successfully upserted: {place_id}")
    except TimeoutError:
        logger.error(f"[upsert_place] Timeout acquiring lock for {path}")
        raise IOError(f"Could not acquire lock to upsert {place_id}")
    except Exception as e:
        logger.error(f"[upsert_place] Failed to upsert {place_id}: {e}")
        raise


def upsert_place_ids(path: str, place_ids: List[str]) -> List[str]:
    """
    Upsert multiple place_ids, creating minimal entries for new ones.
    Uses file locking for atomic operation.
    
    Args:
        path: Path to JSON file
        place_ids: List of place_ids to upsert
        
    Returns:
        List of place_ids that were newly created (not already in JSON)
    """
    logger.info(f"[upsert_place_ids] Starting upsert for {len(place_ids)} place_ids")
    
    try:
        with file_lock(path, timeout=10.0):
            places = load_places_json(path, use_lock=False)  # Already locked
            logger.debug(f"[upsert_place_ids] Loaded {len(places)} existing places from JSON")
            
            # Check if JSON was corrupted (returned empty when it shouldn't be)
            if len(places) == 0 and os.path.exists(path) and os.path.getsize(path) > 100:
                # File exists and has content but couldn't be parsed - this is corruption
                logger.error(f"[upsert_place_ids] WARNING: JSON file appears corrupted (has {os.path.getsize(path)} bytes but loaded 0 places)")
                # Don't proceed - this would overwrite all existing data
                raise ValueError(f"JSON file at {path} is corrupted and cannot be loaded. A backup may have been created at {path}.corrupted_backup")
            
            new_place_ids = []
            existing_place_ids = []
            
            for place_id in place_ids:
                if place_id not in places:
                    # Create minimal entry
                    logger.debug(f"[upsert_place_ids] Creating new entry for: {place_id}")
                    places[place_id] = {
                        "place_id": place_id,
                        "places_details_flag": False,
                        "tavily_flag": False,
                        "enriched_flag": False,
                        "place": {},
                        "sources": {},
                        "derived": {}
                    }
                    new_place_ids.append(place_id)
                else:
                    existing_place_ids.append(place_id)
                    logger.debug(f"[upsert_place_ids] Place already exists: {place_id}")
            
            logger.info(f"[upsert_place_ids] Created {len(new_place_ids)} new entries, {len(existing_place_ids)} already existed")
            
            logger.debug(f"[upsert_place_ids] Total places before save: {len(places)}")
            
            save_places_json(path, places, use_lock=False)  # Already locked
            
            # Verify after save (without lock since we're done)
            verify_places = load_places_json(path, use_lock=True)
            logger.debug(f"[upsert_place_ids] Verified after save: {len(verify_places)} places in file")
            
            return new_place_ids
    except TimeoutError:
        logger.error(f"[upsert_place_ids] Timeout acquiring lock for {path}")
        raise IOError(f"Could not acquire lock to upsert place_ids")
    except Exception as e:
        logger.error(f"[upsert_place_ids] Failed to upsert place_ids: {e}")
        raise


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
                place["tavily_flag"] = False  # Reset tavily_flag when clearing data
                logger.debug(f"[reset_enrichment_flag] Cleared enrichment data for {place_id}")
            
            reset_count += 1
    
    if reset_count > 0:
        save_places_json(json_path, places)
        logger.info(f"[reset_enrichment_flag] Successfully reset {reset_count} places")
    else:
        logger.info(f"[reset_enrichment_flag] No places needed resetting")
    
    return reset_count

