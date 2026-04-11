"""
Google Places API wrapper for V2.

Two uses only:
  1. Nearby Search (map pan hot path) — fires 3 concurrent type requests
  2. Text Search (place resolver) — used by crawler only

Never requests reviews, photos, opening_hours, or editorial summaries —
those trigger Enterprise SKU billing (~$0.040/req vs ~$0.006/req basic).
"""
from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Nearby field mask — Basic + Atmosphere + Advanced tiers
# primaryType is Basic; rating/userRatingCount are Atmosphere; regularOpeningHours is Advanced
NEARBY_FIELD_MASK = (
    "places.id,places.displayName,places.location,places.types,places.photos,"
    "places.primaryType,places.rating,places.userRatingCount,places.regularOpeningHours"
)
TEXT_SEARCH_FIELD_MASK = "places.id,places.displayName,places.location,places.formattedAddress"


def _photo_urls(place: dict, api_key: str, max_photos: int = 3) -> list[str]:
    """Convert Google Places photo resource names to usable media URLs."""
    photos = place.get("photos", [])[:max_photos]
    urls = []
    for photo in photos:
        name = photo.get("name", "")
        if name:
            urls.append(
                f"https://places.googleapis.com/v1/{name}/media"
                f"?maxHeightPx=600&maxWidthPx=800&key={api_key}"
            )
    return urls


async def nearby_search_parallel(
    lat: float,
    lng: float,
    radius_meters: int,
    api_key: str,
) -> list[dict]:
    """
    Fire 3 concurrent Nearby Search requests (cafe, bakery, library).
    Returns list of {place_id, photo_urls} dicts, deduplicated.

    Note: 'coffee_shop' is NOT a valid nearbysearch type — use 'cafe' only.
    Do not combine rankby=distance and radius — mutually exclusive.
    """
    types = ["cafe", "bakery", "library"]

    async def _search_one(place_type: str, client: httpx.AsyncClient) -> list[dict]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": NEARBY_FIELD_MASK,
        }
        body = {
            "includedTypes": [place_type],
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(radius_meters),
                }
            },
            "maxResultCount": 20,
        }
        try:
            resp = await client.post(NEARBY_SEARCH_URL, headers=headers, json=body, timeout=10)
            resp.raise_for_status()
            return [
                {
                    "place_id": p["id"],
                    "photo_urls": _photo_urls(p, api_key),
                    "primary_type": p.get("primaryType"),
                    "rating": p.get("rating"),
                    "user_rating_count": p.get("userRatingCount"),
                    "regular_opening_hours": p.get("regularOpeningHours"),
                }
                for p in resp.json().get("places", [])
                if "id" in p
            ]
        except Exception as exc:
            logger.warning("Nearby Search failed for type=%s: %s", place_type, exc)
            return []

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_search_one(t, client) for t in types])

    seen: set[str] = set()
    deduplicated: list[dict] = []
    for places in results:
        for p in places:
            pid = p["place_id"]
            if pid not in seen:
                seen.add(pid)
                deduplicated.append(p)

    return deduplicated


async def text_search(
    query: str,
    location_bias: dict,
    api_key: str,
) -> list[dict]:
    """
    Text Search for place resolver. Returns list of {place_id, name, lat, lng, address}.
    Basic fields only — never requests reviews, photos, or editorial summaries.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": TEXT_SEARCH_FIELD_MASK,
    }
    body: dict = {"textQuery": query, "maxResultCount": 5}
    if location_bias:
        body["locationBias"] = location_bias

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(TEXT_SEARCH_URL, headers=headers, json=body, timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Text Search failed for query=%r: %s", query, exc)
            return []

    places = []
    for p in resp.json().get("places", []):
        loc = p.get("location", {})
        name_obj = p.get("displayName", {})
        places.append({
            "place_id": p.get("id", ""),
            "name": name_obj.get("text", "") if isinstance(name_obj, dict) else str(name_obj),
            "lat": loc.get("latitude"),
            "lng": loc.get("longitude"),
            "formatted_address": p.get("formattedAddress", ""),
        })
    return places
