"""
Database service for reading place data.

Replaces json_service.py with database-backed service.
"""

import logging
from typing import Dict, List

from backend.enrichment.db_storage import load_places, load_all_places

logger = logging.getLogger(__name__)


def get_places_data(place_ids: List[str]) -> Dict[str, Dict]:
    """
    Get place data for given place_ids from database.
    
    Args:
        place_ids: List of place_ids to retrieve
        
    Returns:
        Dictionary keyed by place_id with place data
    """
    if not place_ids:
        return {}
    
    return load_places(place_ids)


def get_all_places() -> Dict[str, Dict]:
    """
    Get all places from database.
    
    Returns:
        Dictionary keyed by place_id with all place data
    """
    return load_all_places()


def get_enrichment_status(place_ids: List[str]) -> Dict[str, Dict]:
    """
    Get enrichment status for given place_ids.
    
    Args:
        place_ids: List of place_ids to check
        
    Returns:
        Dictionary with enrichment status for each place_id
        Format: {"place_id": {"places_details_flag": bool, "tavily_flag": bool, "enriched_flag": bool}}
    """
    if not place_ids:
        return {}
    
    places = load_places(place_ids)
    status = {}
    
    for pid in place_ids:
        if pid in places:
            place = places[pid]
            status[pid] = {
                "places_details_flag": place.get("places_details_flag", False),
                "tavily_flag": place.get("tavily_flag", False),
                "enriched_flag": place.get("enriched_flag", False),
            }
        else:
            status[pid] = {
                "places_details_flag": False,
                "tavily_flag": False,
                "enriched_flag": False,
            }
    
    return status

