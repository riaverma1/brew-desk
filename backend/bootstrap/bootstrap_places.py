import json
import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import os
import requests

PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

@dataclass
class Config:
    api_key: str

    # Center point
    lat: float
    lng: float

    # Bootstrap area
    radius_m: int = 1200          # overall area you want to cover around the center
    grid_step_m: int = 400        # spacing between grid points (smaller = more coverage, more calls)
    nearby_search_radius_m: int = 300  # radius used for each nearby search call around each grid point

    # Candidate inclusion
    include_types: Tuple[str, ...] = ("cafe", "restaurant", "library", "bakery", "lodging")
    keyword: Optional[str] = None  # e.g. "coffee" (optional, can reduce noise)
    max_places_to_enrich: int = 200  # safety cap for your first run

    # Throttling
    request_sleep_s: float = 0.2   # be gentle with rate limits


def meters_to_lat_deg(m: float) -> float:
    return m / 111_320.0


def meters_to_lng_deg(m: float, lat: float) -> float:
    # longitude degrees shrink by cos(latitude)
    return m / (111_320.0 * math.cos(math.radians(lat)))


def grid_points(center_lat: float, center_lng: float, radius_m: int, step_m: int) -> List[Tuple[float, float]]:
    dlat = meters_to_lat_deg(step_m)
    dlng = meters_to_lng_deg(step_m, center_lat)

    # number of steps to cover radius in each direction
    n = max(1, int(math.ceil(radius_m / step_m)))

    points = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            lat = center_lat + i * dlat
            lng = center_lng + j * dlng
            points.append((lat, lng))
    return points


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


def extract_signals(details: Dict) -> Dict:
    # Very basic heuristic v0: scan review text for keywords.
    reviews = details.get("reviews", []) or []
    text = " ".join([(rv.get("text") or "") for rv in reviews]).lower()

    wifi_hits = ["wifi", "wi-fi", "internet"]
    laptop_hits = ["laptop", "work", "working", "study", "studying", "remote", "wfh"]
    outlet_hits = ["outlet", "outlets", "plug", "plugs", "socket", "sockets", "charging"]
    noise_hits = ["quiet", "calm", "peaceful", "noisy", "loud", "crowded", "busy"]

    def count_hits(phrases: List[str]) -> int:
        return sum(text.count(p) for p in phrases)

    wifi = count_hits(wifi_hits)
    laptop = count_hits(laptop_hits)
    outlets = count_hits(outlet_hits)
    noise = count_hits(noise_hits)

    # crude scores
    wifi_score = min(1.0, wifi / 2.0)                 # 2+ mentions -> 1.0
    laptop_score = min(1.0, laptop / 3.0)             # 3+ mentions -> 1.0
    outlets_score = min(1.0, outlets / 2.0)

    # confidence: how much evidence you actually saw
    evidence_total = wifi + laptop + outlets
    confidence = "low"
    if evidence_total >= 5:
        confidence = "high"
    elif evidence_total >= 2:
        confidence = "medium"

    # Evidence snippets: store a couple reviews that contain key terms
    evidence_reviews = []
    for rv in reviews:
        t = (rv.get("text") or "").lower()
        if any(k in t for k in ["wifi", "wi-fi", "laptop", "outlet", "work", "study"]):
            evidence_reviews.append({
                "author_name": rv.get("author_name"),
                "rating": rv.get("rating"),
                "relative_time_description": rv.get("relative_time_description"),
                "text": rv.get("text"),
            })
        if len(evidence_reviews) >= 3:
            break

    return {
        "wifi_score": wifi_score,
        "laptop_friendly_score": laptop_score,
        "outlets_score": outlets_score,
        "confidence": confidence,
        "keyword_counts": {
            "wifi": wifi,
            "laptop_work": laptop,
            "outlets": outlets,
            "noise_terms": noise,
        },
        "evidence_reviews": evidence_reviews,
    }


def run_bootstrap(cfg: Config) -> Dict:
    pts = grid_points(cfg.lat, cfg.lng, cfg.radius_m, cfg.grid_step_m)

    # 1) Collect candidates
    candidates: Dict[str, Dict] = {}  # place_id -> basic nearby result
    for (plat, plng) in pts:
        for t in cfg.include_types:
            time.sleep(cfg.request_sleep_s)
            nearby = nearby_search(cfg, plat, plng, t)

            for item in nearby:
                pid = item.get("place_id")
                if not pid:
                    continue
                # keep the first seen or merge later if you want
                candidates.setdefault(pid, item)

    place_ids = list(candidates.keys())
    print(f"Collected {len(place_ids)} unique place_ids")

    # 2) Enrich (cap for your first test)
    enriched = []
    for i, pid in enumerate(place_ids[: cfg.max_places_to_enrich], start=1):
        time.sleep(cfg.request_sleep_s)
        details = place_details(cfg, pid)
        signals = extract_signals(details)

        enriched.append({
            "place_id": pid,
            "google_details": details,
            "wfh_attributes_v0": signals,
            "ingested_at_epoch": int(time.time()),
        })

        if i % 25 == 0:
            print(f"Enriched {i}/{min(len(place_ids), cfg.max_places_to_enrich)}")

    return {
        "bootstrap_center": {"lat": cfg.lat, "lng": cfg.lng},
        "config": cfg.__dict__,
        "candidate_count": len(place_ids),
        "enriched_count": len(enriched),
        "places": enriched,
    }


if __name__ == "__main__":
    # TODO: fill these in
    cfg = Config(
        api_key=PLACES_API_KEY,
        lat=40.7128,
        lng=-74.0060,
        radius_m=1200,
        grid_step_m=400,
        nearby_search_radius_m=300,
        include_types=("cafe", "restaurant", "library", "bakery", "lodging"),
        keyword=None,  # or "coffee"
        max_places_to_enrich=150,
        request_sleep_s=0.25,
    )

    out = run_bootstrap(cfg)

    with open("places_bootstrap.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Wrote places_bootstrap.json")

def bootstrap_to_json(
    api_key: str,
    lat: float,
    lng: float,
    out_path: str = "places_bootstrap.json",
    **cfg_kwargs,
):
    cfg = Config(
        api_key=api_key,
        lat=lat,
        lng=lng,
        **cfg_kwargs,
    )

    out = run_bootstrap(cfg)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return out
