"""
Pure filter: takes a raw Google place_id list, returns only DB-matched
eligible places that meet score and laptop confidence thresholds.
"""
from __future__ import annotations

from models.place import PlacePinResponse
from services import supabase_client


async def filter_eligible_places(
    candidate_place_ids: list[str],
    score_threshold: float,
    laptop_confidence_threshold: float,
) -> list[PlacePinResponse]:
    if not candidate_place_ids:
        return []

    rows = await supabase_client.get_places_by_ids(
        candidate_place_ids, score_threshold, laptop_confidence_threshold
    )

    return [
        PlacePinResponse(
            place_id=row["place_id"],
            name=row["name"],
            address=row.get("address"),
            lat=row["lat"],
            lng=row["lng"],
            wfh_score=row["wfh_score"],
            has_wifi=row.get("has_wifi"),
            has_outlets=row.get("has_outlets"),
            is_laptop_friendly=row.get("is_laptop_friendly"),
            noise_level=row.get("noise_level"),
            seating_comfort=row.get("seating_comfort"),
            mention_count=row["mention_count"],
            source_count=row["source_count"],
            photos=row.get("photos") or [],
            primary_type=row.get("primary_type"),
            rating=row.get("rating"),
            user_rating_count=row.get("user_rating_count"),
            regular_opening_hours=row.get("regular_opening_hours"),
        )
        for row in rows
    ]
