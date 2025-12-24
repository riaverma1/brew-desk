import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from backend.enrichment.types import Config
from backend.enrichment.google_places import nearby_search_with_sync
from backend.enrichment.geo import grid_points
import os

PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")


def run_bootstrap(cfg: Config) -> Dict:
    """
    Run bootstrap: collect places using nearby_search with sync enrichment.
    This only does sync operations (nearby_search + place_details).
    Async enrichment (Tavily) should be run separately.
    """
    pts = grid_points(cfg.lat, cfg.lng, cfg.radius_m, cfg.grid_step_m)

    # 1) Collect candidates using nearby_search_with_sync
    # This automatically upserts to JSON and optionally fetches place_details
    all_place_ids = set()
    for (plat, plng) in pts:
        # Create a temporary config for this grid point
        from backend.enrichment.types import Config
        grid_cfg = Config(
            api_key=cfg.api_key,
            lat=plat,
            lng=plng,
            radius_m=cfg.radius_m,
            grid_step_m=cfg.grid_step_m,
            nearby_search_radius_m=cfg.nearby_search_radius_m,
            include_types=cfg.include_types,
            keyword=cfg.keyword,
            max_places_to_enrich=cfg.max_places_to_enrich,
            request_sleep_s=cfg.request_sleep_s,
        )
        
        for t in cfg.include_types:
            time.sleep(cfg.request_sleep_s)
            # Use nearby_search_with_sync which handles JSON upsert and place_details
            nearby = nearby_search_with_sync(grid_cfg, t, auto_enrich_sync=True)
            
            for item in nearby:
                pid = item.get("id")  # New API uses "id" instead of "place_id"
                if pid:
                    all_place_ids.add(pid)

    place_ids = list(all_place_ids)
    print(f"Collected {len(place_ids)} unique place_ids")
    
    # Note: Sync enrichment (place_details) is already done by nearby_search_with_sync
    # Async enrichment (Tavily + LLM) should be run separately using:
    #   from backend.enrichment.places_manager import process_enrichment_async
    #   process_enrichment_async(cfg, place_ids=place_ids[:cfg.max_places_to_enrich])
    
    # Return summary
    return {
        "bootstrap_center": {"lat": cfg.lat, "lng": cfg.lng},
        "config": cfg.__dict__,
        "candidate_count": len(place_ids),
        "message": "Sync enrichment complete. Run async enrichment separately using process_enrichment_async()",
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
