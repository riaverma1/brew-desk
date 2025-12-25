"""
Migration script to add tavily_flag to existing places in JSON file.

This script:
1. Adds tavily_flag to all places based on whether they have Tavily data
2. Updates enriched_flag to False if tavily_flag is False (even if derived attributes exist)
3. Fixes any inconsistencies in existing flags
"""
import logging
from backend.enrichment.json_storage import load_places_json, save_places_json

logger = logging.getLogger(__name__)


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
        logger.info("[migrate_tavily_flag] No places found in JSON file")
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
            logger.debug(f"[migrate_tavily_flag] Added tavily_flag={has_tavily_results} for {place_id}")
        else:
            # Check if existing tavily_flag is correct
            existing_tavily_flag = place.get("tavily_flag", False)
            if existing_tavily_flag != has_tavily_results:
                place["tavily_flag"] = has_tavily_results
                updated = True
                stats["tavily_flag_fixed"] += 1
                logger.info(f"[migrate_tavily_flag] Fixed tavily_flag for {place_id}: {existing_tavily_flag} -> {has_tavily_results}")
        
        # Fix enriched_flag: should only be True if tavily_flag is True
        tavily_flag = place.get("tavily_flag", False)
        enriched_flag = place.get("enriched_flag", False)
        
        if enriched_flag and not tavily_flag:
            # enriched_flag is True but tavily_flag is False - fix it
            place["enriched_flag"] = False
            updated = True
            stats["enriched_flag_fixed"] += 1
            logger.info(f"[migrate_tavily_flag] Fixed enriched_flag for {place_id}: set to False (no Tavily data)")
        
        if updated:
            stats["updated_count"] += 1
    
    if stats["updated_count"] > 0:
        save_places_json(json_path, places)
        logger.info(f"[migrate_tavily_flag] Successfully migrated {stats['updated_count']} places")
        logger.info(f"[migrate_tavily_flag] Summary: {stats}")
    else:
        logger.info(f"[migrate_tavily_flag] No places needed migration")
    
    return stats


if __name__ == "__main__":
    import sys
    import os
    import json
    from pathlib import Path
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Default path
    default_path = os.path.join(
        Path(__file__).resolve().parent.parent,
        "data",
        "places_bootstrap.json"
    )
    
    json_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    
    print(f"Starting migration for: {json_path}")
    print("=" * 60)
    
    stats = migrate_tavily_flag(json_path)
    
    print("=" * 60)
    print("Migration Summary:")
    print(f"  Total places: {stats['total_places']}")
    print(f"  Places updated: {stats['updated_count']}")
    print(f"  tavily_flag added: {stats['tavily_flag_added']}")
    print(f"  tavily_flag fixed: {stats['tavily_flag_fixed']}")
    print(f"  enriched_flag fixed: {stats['enriched_flag_fixed']}")
    print("=" * 60)

