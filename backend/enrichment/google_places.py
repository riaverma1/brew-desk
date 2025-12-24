from pathlib import Path
from backend.enrichment.types import Config
import requests
import time
from typing import Dict, List
import os
import dotenv


PLACES_SEARCH_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
PLACES_DETAILS_BASE_URL = "https://places.googleapis.com/v1/places"

dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")
PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")


def debug_place_apis(cfg: Config, place_id: str, search_location: tuple = None) -> None:
    """
    Debug function to test both nearby_search and place_details APIs for a specific place_id.
    
    Args:
        cfg: Config object
        place_id: Place ID to test
        search_location: Optional (lat, lng) tuple to use for nearby_search. 
                         If None, uses cfg.lat and cfg.lng
    """
    print(f"\n{'#'*70}")
    print(f"# DEBUGGING PLACE APIs FOR: {place_id}")
    print(f"{'#'*70}\n")
    
    # First, try to find this place in nearby_search
    if search_location:
        test_lat, test_lng = search_location
    else:
        test_lat, test_lng = cfg.lat, cfg.lng
    
    print(f"Step 1: Testing nearby_search near ({test_lat}, {test_lng})")
    print("-" * 70)
    
    # Create a temporary config for nearby_search
    from backend.enrichment.types import Config
    search_cfg = Config(
        api_key=cfg.api_key,
        lat=test_lat,
        lng=test_lng,
        radius_m=cfg.radius_m,
        grid_step_m=cfg.grid_step_m,
        nearby_search_radius_m=5000,  # Large radius to find the place
        include_types=("cafe",),
        keyword=None,
        max_places_to_enrich=cfg.max_places_to_enrich,
        request_sleep_s=cfg.request_sleep_s,
    )
    
    nearby_results = nearby_search(search_cfg, place_type="cafe", debug=True)
    
    # Find our specific place in the results
    target_result = None
    for result in nearby_results:
        if result.get("id") == place_id:
            target_result = result
            break
    
    if target_result:
        print(f"\n✓ Found {place_id} in nearby_search results!")
        display_name = target_result.get('displayName', {})
        print(f"  DisplayName: {_normalize_display_name(display_name)}")
        print(f"\n  All keys in nearby_search result:")
        for key in sorted(target_result.keys()):
            value = target_result.get(key)
            if isinstance(value, (dict, list)):
                print(f"    - {key}: {type(value).__name__} (len={len(value) if hasattr(value, '__len__') else 'N/A'})")
            else:
                print(f"    - {key}: {value}")
        
        # Check binary attributes specifically
        binary_attrs = ["restroom", "servesCoffee", "goodForGroups", "parkingOptions", "accessibilityOptions", "outdoorSeating"]
        print(f"\n  Binary attributes in nearby_search result:")
        for attr in binary_attrs:
            value = target_result.get(attr)
            if value is not None:
                print(f"    ✓ {attr}: {value}")
            else:
                print(f"    ✗ {attr}: NOT FOUND")
    else:
        print(f"\n✗ Place {place_id} NOT found in nearby_search results")
        print(f"  (Searched {len(nearby_results)} results)")
    
    # Now test place_details
    print(f"\n\nStep 2: Testing place_details for {place_id}")
    print("-" * 70)
    
    details_result = place_details(cfg, place_id, debug=True)
    
    # Check binary attributes in place_details
    binary_attrs = ["restroom", "servesCoffee", "goodForGroups", "parkingOptions", "accessibilityOptions", "outdoorSeating"]
    print(f"\nBinary attributes in place_details response:")
    for attr in binary_attrs:
        value = details_result.get(attr)
        if value is not None:
            print(f"  ✓ {attr}: {value}")
        else:
            print(f"  ✗ {attr}: NOT FOUND")
    
    # Summary
    print(f"\n\n{'#'*70}")
    print(f"# SUMMARY")
    print(f"{'#'*70}")
    print(f"Place ID: {place_id}")
    display_name = details_result.get('displayName', {})
    print(f"Place DisplayName: {_normalize_display_name(display_name)}")
    print(f"\nBinary attributes available:")
    print(f"  From nearby_search: {[attr for attr in binary_attrs if target_result and target_result.get(attr) is not None] if target_result else 'N/A'}")
    print(f"  From place_details: {[attr for attr in binary_attrs if details_result.get(attr) is not None]}")
    print(f"{'#'*70}\n")

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


def nearby_search(cfg: Config, place_type: str, debug: bool = False) -> List[Dict]:
    """
    Search for nearby places using the new Places API v1 searchNearby endpoint.
    
    Args:
        cfg: Config object
        place_type: Place type to search for (e.g., "cafe")
        debug: If True, print detailed debugging information
        
    Returns:
        List of place dictionaries in new API format (id, displayName, formattedAddress, location, etc.)
    """
    if debug:
        print(f"\n{'='*60}")
        print(f"DEBUG: [nearby_search] Searching for type: {place_type}")
        print(f"DEBUG: [nearby_search] Location: ({cfg.lat}, {cfg.lng}), Radius: {cfg.nearby_search_radius_m}")
        print(f"{'='*60}")
    
    # Prepare request headers
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": cfg.api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.types,places.rating,places.userRatingCount,places.priceLevel,places.businessStatus,places.regularOpeningHours,places.websiteUri,places.restroom,places.servesCoffee,places.goodForGroups,places.parkingOptions,places.accessibilityOptions,places.outdoorSeating"
    }
    
    # Prepare base request body (will be copied for each request)
    base_body = {
        "includedTypes": [place_type],
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": cfg.lat,
                    "longitude": cfg.lng
                },
                "radius": cfg.nearby_search_radius_m
            }
        },
        "maxResultCount": 20  # Default max results per page
    }
    
    # Add keyword if specified
    if cfg.keyword:
        base_body["keyword"] = cfg.keyword
    
    results: List[Dict] = []
    page_token = None
    
    while True:
        # Create a copy of the body for this request
        body = base_body.copy()
        
        # Add page token if available
        if page_token:
            body["pageToken"] = page_token
            # Google requires a short delay before the next_page_token becomes valid
            time.sleep(2.0)
        
        r = requests.post(PLACES_SEARCH_NEARBY_URL, headers=headers, json=body, timeout=30)
        
        if r.status_code != 200:
            error_text = r.text
            if debug:
                print(f"DEBUG: [nearby_search] ERROR: status_code={r.status_code}, response={error_text}")
            raise RuntimeError(f"Nearby Search failed: status_code={r.status_code}, error={error_text}")
        
        data = r.json()
        
        # The new API returns places in a "places" array
        page_results = data.get("places", [])
        results.extend(page_results)
        
        if debug and page_results:
            print(f"DEBUG: [nearby_search] Found {len(page_results)} results on this page")
            # Check first result for binary attributes
            first_result = page_results[0]
            print(f"DEBUG: [nearby_search] First result keys: {list(first_result.keys())}")
            print(f"DEBUG: [nearby_search] First result id: {first_result.get('id')}")
            display_name = first_result.get('displayName', {})
            print(f"DEBUG: [nearby_search] First result displayName: {_normalize_display_name(display_name)}")
            
            # Check for binary attributes in nearby_search response
            binary_attrs_to_check = ["restroom", "servesCoffee", "goodForGroups", "parkingOptions", "accessibilityOptions", "outdoorSeating"]
            print(f"\nDEBUG: [nearby_search] Binary attributes in first result:")
            for attr in binary_attrs_to_check:
                value = first_result.get(attr)
                print(f"  - {attr}: {value} (type: {type(value).__name__})")
        
        # Check for next page token
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    
    if debug:
        print(f"DEBUG: [nearby_search] Total results: {len(results)}")
        print(f"{'='*60}\n")
    
    return results


def place_details(cfg: Config, place_id: str, debug: bool = False) -> Dict:
    """
    Fetch place details using the new Places API v1 endpoint.
    
    Args:
        cfg: Config object
        place_id: Place ID to fetch details for
        debug: If True, print detailed debugging information
        
    Returns:
        Place dictionary in new API format (id, displayName, formattedAddress, location, etc.)
    """
    if debug:
        print(f"\n{'='*60}")
        print(f"DEBUG: [place_details] Fetching details for place_id: {place_id}")
        print(f"{'='*60}")
    
    # Construct URL for place details
    url = f"{PLACES_DETAILS_BASE_URL}/{place_id}"
    
    # Prepare request headers
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": cfg.api_key,
        "X-Goog-FieldMask": "displayName,formattedAddress,location,types,rating,userRatingCount,priceLevel,businessStatus,regularOpeningHours,websiteUri,reviews,restroom,servesCoffee,goodForGroups,parkingOptions,accessibilityOptions,outdoorSeating"
    }
    
    if debug:
        print(f"DEBUG: [place_details] API URL: {url}")
        print(f"DEBUG: [place_details] Using field mask in header")
    
    r = requests.get(url, headers=headers, timeout=30)
    
    if r.status_code != 200:
        error_text = r.text
        if debug:
            print(f"DEBUG: [place_details] ERROR: status_code={r.status_code}, response={error_text}")
        raise RuntimeError(f"Place Details failed: status_code={r.status_code}, error={error_text}")
    
    data = r.json()
    
    # Ensure id field is set (API returns it, but ensure consistency)
    if "id" not in data:
        data["id"] = place_id
    
    if debug:
        print(f"DEBUG: [place_details] Response status_code: {r.status_code}")
        print(f"DEBUG: [place_details] Result keys: {list(data.keys())}")
        display_name = data.get('displayName', {})
        print(f"DEBUG: [place_details] Place displayName: {_normalize_display_name(display_name)}")
        
        # Check for binary attributes in place_details response
        binary_attrs_to_check = ["restroom", "servesCoffee", "goodForGroups", "parkingOptions", "accessibilityOptions", "outdoorSeating"]
        print(f"\nDEBUG: [place_details] Binary attributes in place_details response:")
        for attr in binary_attrs_to_check:
            value = data.get(attr)
            print(f"  - {attr}: {value} (type: {type(value).__name__})")
        
        print(f"{'='*60}\n")
    
    return data




def nearby_search_with_sync(cfg: Config, place_type: str, auto_enrich_sync: bool = True) -> List[Dict]:
    """
    Wrapper around nearby_search that optionally triggers sync enrichment.
    
    Args:
        cfg: Config object
        place_type: Place type to search for
        auto_enrich_sync: If True, automatically process results and upsert to JSON
        
    Returns:
        Original nearby_search results (unchanged)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[nearby_search_with_sync] Starting nearby_search for type: {place_type}")
    print(f"DEBUG: [nearby_search_with_sync] Starting nearby_search for type: {place_type}")
    print(f"DEBUG: [nearby_search_with_sync] auto_enrich_sync: {auto_enrich_sync}")
    
    results = nearby_search(cfg, place_type)
    logger.info(f"[nearby_search_with_sync] Found {len(results)} results from nearby_search")
    print(f"DEBUG: [nearby_search_with_sync] Found {len(results)} results from nearby_search")
    
    if len(results) > 0:
        sample_result = results[0]
        print(f"DEBUG: [nearby_search_with_sync] Sample result keys: {list(sample_result.keys())}")
        print(f"DEBUG: [nearby_search_with_sync] Sample result id: {sample_result.get('id')}")
        display_name = sample_result.get('displayName', {})
        print(f"DEBUG: [nearby_search_with_sync] Sample result displayName: {_normalize_display_name(display_name)}")
    
    if auto_enrich_sync:
        logger.info(f"[nearby_search_with_sync] Calling process_nearby_search_sync...")
        print(f"DEBUG: [nearby_search_with_sync] Calling process_nearby_search_sync...")
        # Import here to avoid circular dependencies
        from backend.enrichment.places_manager import process_nearby_search_sync
        processed = process_nearby_search_sync(cfg, results)
        logger.info(f"[nearby_search_with_sync] Processed {len(processed)} places")
        print(f"DEBUG: [nearby_search_with_sync] Processed {len(processed)} places")
    else:
        logger.info(f"[nearby_search_with_sync] Skipping sync enrichment (auto_enrich_sync=False)")
        print(f"DEBUG: [nearby_search_with_sync] Skipping sync enrichment")
    
    return results
