from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class MapBounds(BaseModel):
    north: float
    south: float
    east: float
    west: float


class NearbySearchRequest(BaseModel):
    lat: float
    lng: float
    bounds: MapBounds


NoiseLevel = Literal["quiet", "moderate", "loud"]


class PlacePinResponse(BaseModel):
    place_id: str
    name: str
    address: str | None = None
    lat: float
    lng: float
    wfh_score: float
    has_wifi: bool | None = None
    has_outlets: bool | None = None
    is_laptop_friendly: bool | None = None
    noise_level: NoiseLevel | None = None
    seating_comfort: str | None = None
    mention_count: int
    source_count: int
    photos: list[str] = []
    primary_type: str | None = None
    rating: float | None = None
    user_rating_count: int | None = None
    regular_opening_hours: dict | None = None
    top_mention_snippet: str | None = None


class NearbySearchResponse(BaseModel):
    places: list[PlacePinResponse]
    region_status: Literal["seeded", "crawling", "cold"] | None = None
    region_id: str | None = None
