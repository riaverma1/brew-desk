import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from backend.enrichment.types import Config
from backend.enrichment.google_places import nearby_search, place_details
from backend.enrichment.scoring import extract_signals
from backend.enrichment.geo import grid_points
import os

PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")


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
        fetched_at = datetime.now(timezone.utc).isoformat()

        location = (details.get("geometry") or {}).get("location") or {}
        place_block = {
            "name": details.get("name"),
            "lat": location.get("lat"),
            "lng": location.get("lng"),
            "types": details.get("types") or [],
            "formatted_address": details.get("formatted_address"),
        }

        wfh_attributes = {
            "wifi_score": signals.get("wifi_score"),
            "outlets_score": signals.get("outlets_score"),
            "laptop_friendly": (signals.get("laptop_friendly_score") or 0) >= 0.5,
            "noise_level": "unknown",
            "confidence": signals.get("confidence_numeric", 0.0),
        }

        enriched.append({
            "place_id": pid,
            "place": place_block,
            "sources": {
                "google_details": {
                    "fetched_at": fetched_at,
                    "payload": details,
                },
                "google_reviews": {
                    "fetched_at": fetched_at,
                    "reviews": details.get("reviews", []),
                },
                "tavily": {
                    "fetched_at": None,
                    "query": None,
                    "results": [],
                    "excerpts": [],
                },
            },
            "derived": {
                "wfh_attributes": wfh_attributes,
                "summary": signals.get("summary", ""),
                "derived_at": datetime.now(timezone.utc).isoformat(),
                "deriver_version": "signals_v0.1",
            },
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

if __name__ == "__main__":
    cfg = Config(
        api_key=PLACES_API_KEY,
        lat=40.7128,
        lng=-74.0060,
        radius_m=1200,
        grid_step_m=400,
        nearby_search_radius_m=300,
        include_types=("cafe", "restaurant", "library", "bakery", "lodging"),
        keyword=None,  
        max_places_to_enrich=150,
        request_sleep_s=0.25,
    )

    out = run_bootstrap(cfg)

    with open("places_bootstrap.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Wrote places_bootstrap.json")
