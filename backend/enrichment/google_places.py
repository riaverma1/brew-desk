from backend.enrichment.types import Config
import requests
import time
from typing import Dict, List
import os


PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

def nearby_search(cfg: Config, lat: float, lng: float, place_type: str) -> List[Dict]:
    params = {
        "key": cfg.api_key,
        "location": f"{lat},{lng}",
        "radius": cfg.nearby_search_radius_m,
        "type": place_type,
    }
    if cfg.keyword:
        params["keyword"] = cfg.keyword

    results: List[Dict] = []
    page_token = None

    while True:
        if page_token:
            params["pagetoken"] = page_token
            # Google requires a short delay before the next_page_token becomes valid
            time.sleep(2.0)

        r = requests.get(PLACES_NEARBY_URL, params=params, timeout=30)
        data = r.json()

        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            # Common: OVER_QUERY_LIMIT, REQUEST_DENIED, INVALID_REQUEST
            raise RuntimeError(f"Nearby Search failed: status={status}, error={data.get('error_message')}")

        results.extend(data.get("results", []))

        page_token = data.get("next_page_token")
        if not page_token:
            break

    return results


def place_details(cfg: Config, place_id: str) -> Dict:
    # Keep fields tight to control cost/latency.
    fields = ",".join([
        "place_id",
        "name",
        "geometry/location",
        "types",
        "rating",
        "user_ratings_total",
        "price_level",
        "business_status",
        "opening_hours",
        "website",
        "formatted_address",
        "reviews",  # may be absent for many places
    ])

    params = {
        "key": cfg.api_key,
        "place_id": place_id,
        "fields": fields,
        "reviews_no_translations": "true",
    }

    r = requests.get(PLACES_DETAILS_URL, params=params, timeout=30)
    data = r.json()

    status = data.get("status")
    if status != "OK":
        raise RuntimeError(f"Place Details failed: status={status}, error={data.get('error_message')}")

    return data["result"]
