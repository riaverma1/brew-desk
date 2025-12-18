from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class Config:
    api_key: str
    lat: float
    lng: float
    radius_m: int = 1200
    grid_step_m: int = 400
    nearby_search_radius_m: int = 300
    include_types: Tuple[str, ...] = ("cafe", "restaurant", "library", "bakery", "lodging")
    keyword: Optional[str] = None
    max_places_to_enrich: int = 200
    request_sleep_s: float = 0.2
