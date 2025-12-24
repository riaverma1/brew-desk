#!/usr/bin/env python3
"""
Standalone migration script to add tavily_flag to existing places in JSON file.
This script avoids importing the full backend module to prevent import errors.
"""
import json
import os
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_places_json(path: str) -> dict:
    """Load JSON file, return dictionary keyed by place_id."""
    if not os.path.exists(path):
        logger.info(f"File does not exist: {path}")
        return {}
    
    file_size = os.path.getsize(path)
    if file_size == 0:
        logger.info(f"File is empty: {path}")
        return {}
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Ensure it's a dictionary keyed by place_id
        if isinstance(data, dict):
            return data
        elif isinstance(data, list):
            # Convert old array format to dict format
            result = {}
            for place in data:
                place_id = place.get("place_id")
                if place_id:
                    result[place_id] = place
            return result
        else:
            logger.warning(f"Unexpected data type: {type(data)}")
            return {}
    except Exception as e:
        logger.error(f"Error loading JSON: {e}")
        raise


def save_places_json(path: str, places: dict) -> None:
    """Save dictionary to JSON file with atomic write."""
    # Ensure directory exists
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    
    # Use atomic write: write to temp file, then rename
    temp_path = path + ".tmp"
    
    try:
        # Write to temporary file first
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(places, f, ensure_ascii=False, indent=2)
        
        # Atomic rename
        os.replace(temp_path, path)
        logger.info(f"Successfully saved {len(places)} places to {path}")
    except Exception as e:
        logger.error(f"Error saving JSON: {e}")
        # Clean up temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        raise


def migrate_tavily_flag(json_path: str) -> dict:
    """
    Migrate existing places to include tavily_flag and fix enriched_flag.
    
    Args:
        json_path: Path to JSON file
        
    Returns:
        Dictionary with migration statistics
    """
    places = load_places_json(json_path)
    
    if not places:
        logger.info("No places found in JSON file")
        return {
            "total_places": 0,
            "updated_count": 0,
            "tavily_flag_added": 0,
            "tavily_flag_fixed": 0,
            "enriched_flag_fixed": 0,
        }
    
    stats = {
        "total_places": len(places),
        "updated_count": 0,
        "tavily_flag_added": 0,
        "tavily_flag_fixed": 0,
        "enriched_flag_fixed": 0,
    }
    
    for place_id, place in places.items():
        updated = False
        
        # Determine actual Tavily data status
        tavily_data = place.get("sources", {}).get("tavily", {})
        has_tavily_results = bool(
            tavily_data.get("results") and len(tavily_data.get("results", [])) > 0
        )
        
        # Check if tavily_flag exists, if not add it
        if "tavily_flag" not in place:
            place["tavily_flag"] = has_tavily_results
            updated = True
            stats["tavily_flag_added"] += 1
            logger.debug(f"Added tavily_flag={has_tavily_results} for {place_id}")
        else:
            # Check if existing tavily_flag is correct
            existing_tavily_flag = place.get("tavily_flag", False)
            if existing_tavily_flag != has_tavily_results:
                place["tavily_flag"] = has_tavily_results
                updated = True
                stats["tavily_flag_fixed"] += 1
                logger.info(f"Fixed tavily_flag for {place_id}: {existing_tavily_flag} -> {has_tavily_results}")
        
        # Fix enriched_flag: should only be True if tavily_flag is True
        tavily_flag = place.get("tavily_flag", False)
        enriched_flag = place.get("enriched_flag", False)
        
        if enriched_flag and not tavily_flag:
            # enriched_flag is True but tavily_flag is False - fix it
            place["enriched_flag"] = False
            updated = True
            stats["enriched_flag_fixed"] += 1
            logger.info(f"Fixed enriched_flag for {place_id}: set to False (no Tavily data)")
        
        if updated:
            stats["updated_count"] += 1
    
    if stats["updated_count"] > 0:
        save_places_json(json_path, places)
        logger.info(f"Successfully migrated {stats['updated_count']} places")
    else:
        logger.info("No places needed migration")
    
    return stats


if __name__ == "__main__":
    # Default path
    script_dir = Path(__file__).resolve().parent
    default_path = script_dir.parent / "data" / "places_bootstrap.json"
    
    json_path = sys.argv[1] if len(sys.argv) > 1 else str(default_path)
    
    print(f"Starting migration for: {json_path}")
    print("=" * 60)
    
    try:
        stats = migrate_tavily_flag(json_path)
        
        print("=" * 60)
        print("Migration Summary:")
        print(f"  Total places: {stats['total_places']}")
        print(f"  Places updated: {stats['updated_count']}")
        print(f"  tavily_flag added: {stats['tavily_flag_added']}")
        print(f"  tavily_flag fixed: {stats['tavily_flag_fixed']}")
        print(f"  enriched_flag fixed: {stats['enriched_flag_fixed']}")
        print("=" * 60)
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)

