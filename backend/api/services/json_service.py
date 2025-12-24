"""
JSON file service for reading place data.
"""
import os
from pathlib import Path
from typing import Dict, List, Optional
from backend.enrichment.json_storage import load_places_json

# Path to JSON file
DEFAULT_JSON_PATH = os.path.join(
    Path(__file__).resolve().parent.parent.parent,
    "data",
    "places_bootstrap.json"
)


def get_places_data(place_ids: List[str], json_path: str = DEFAULT_JSON_PATH) -> Dict[str, Dict]:
    """
    Get place data for given place_ids from JSON file.
    
    Args:
        place_ids: List of place_ids to retrieve
        json_path: Path to JSON file
        
    Returns:
        Dictionary keyed by place_id with place data
    """
    all_places = load_places_json(json_path)
    return {pid: all_places.get(pid, {}) for pid in place_ids if pid in all_places}


def get_all_places(json_path: str = DEFAULT_JSON_PATH) -> Dict[str, Dict]:
    """
    Get all places from JSON file.
    
    Args:
        json_path: Path to JSON file
        
    Returns:
        Dictionary keyed by place_id with all place data
    """
    return load_places_json(json_path)


def get_enrichment_status(place_ids: List[str], json_path: str = DEFAULT_JSON_PATH) -> Dict[str, Dict]:
    """
    Get enrichment status for given place_ids.
    
    Args:
        place_ids: List of place_ids to check
        json_path: Path to JSON file
        
    Returns:
        Dictionary with enrichment status for each place_id
        Format: {"place_id": {"places_details_flag": bool, "tavily_flag": bool, "enriched_flag": bool}}
    """
    all_places = load_places_json(json_path)
    status = {}
    
    for pid in place_ids:
        if pid in all_places:
            place = all_places[pid]
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

