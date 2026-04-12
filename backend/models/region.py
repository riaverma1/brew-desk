from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class RegionRow(BaseModel):
    id: str
    city_slug: str
    status: Literal["cold", "crawling", "seeded"]
    min_lat: float
    max_lat: float
    min_lng: float
    max_lng: float
    last_crawled_at: str | None = None
    created_at: str
