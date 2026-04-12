"""
Scoring functions for selecting top-n places for enrichment.
"""

import math
from typing import Dict, List


# WFH-friendly type priorities
WFH_TYPE_PRIORS = {
    "cafe": 1.0,
    "coffee_shop": 1.0,
    "library": 1.0,
    "bakery": 0.7,
    "book_store": 0.8,
    "restaurant": 0.4,
    "bar": 0.3,
    "night_club": 0.0,
}


def rating_score(rating: float) -> float:
    """
    Score based on rating: 3.5 -> 0.0, 5.0 -> 1.0 (clamped).
    
    Args:
        rating: Place rating (0-5)
        
    Returns:
        Score between 0.0 and 1.0
    """
    if rating is None:
        return 0.0
    # 3.5 -> 0.0, 5.0 -> 1.0
    return max(0.0, min(1.0, (rating - 3.5) / (5.0 - 3.5)))


def popularity_score(user_ratings_total: int, max_reviews_in_viewport: int) -> float:
    """
    Score based on popularity (number of reviews).
    Uses log to diminish returns of very big chains.
    
    Args:
        user_ratings_total: Number of reviews for this place
        max_reviews_in_viewport: Maximum number of reviews in the viewport
        
    Returns:
        Score between 0.0 and 1.0
    """
    if max_reviews_in_viewport <= 1:
        return 0.0
    if user_ratings_total is None or user_ratings_total <= 0:
        return 0.0
    return math.log1p(user_ratings_total) / math.log1p(max_reviews_in_viewport)


def distance_score(distance_m: float, max_radius_m: float) -> float:
    """
    Score based on distance: closer is better.
    
    Args:
        distance_m: Distance in meters
        max_radius_m: Maximum radius in meters
        
    Returns:
        Score between 0.0 and 1.0 (1.0 = closest, 0.0 = farthest)
    """
    if max_radius_m <= 0:
        return 1.0
    if distance_m is None:
        return 0.5  # Unknown distance gets medium score
    return max(0.0, 1.0 - distance_m / max_radius_m)


def wfh_type_score(types: List[str]) -> float:
    """
    Score based on WFH-friendly types.
    
    Args:
        types: List of place types
        
    Returns:
        Score between 0.0 and 1.0
    """
    if not types:
        return 0.2  # unknown
    scores = [WFH_TYPE_PRIORS.get(t, 0.3) for t in types]
    return max(scores)  # just take the best


def score_place(
    place: Dict,
    user_lat: float,
    user_lng: float,
    max_radius_m: float,
    max_reviews: int,
) -> float:
    """
    Calculate total score for a place by combining all scoring functions.
    
    Args:
        place: Place dictionary with rating, user_ratings_total, types, lat, lng
        user_lat: User's latitude
        user_lng: User's longitude
        max_radius_m: Maximum radius in meters
        max_reviews: Maximum number of reviews in viewport (for normalization)
        
    Returns:
        Total score (weighted combination of all scores)
    """
    place_obj = place.get("place", {})
    
    # Calculate distance
    place_lat = place_obj.get("lat")
    place_lng = place_obj.get("lng")
    distance_m = None
    if place_lat and place_lng and user_lat and user_lng:
        # Haversine formula
        R = 6371000  # Earth radius in meters
        d_lat = math.radians(place_lat - user_lat)
        d_lng = math.radians(place_lng - user_lng)
        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(user_lat))
            * math.cos(math.radians(place_lat))
            * math.sin(d_lng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance_m = R * c
    
    # Get individual scores
    rating = place_obj.get("rating")
    user_ratings_total = place_obj.get("user_ratings_total", 0)
    types = place_obj.get("types", [])
    
    score_rating = rating_score(rating) if rating else 0.0
    score_popularity = popularity_score(user_ratings_total, max_reviews)
    score_distance = distance_score(distance_m, max_radius_m)
    score_type = wfh_type_score(types)
    
    # Combine scores with weights
    # You can adjust these weights based on priorities
    weights = {
        "rating": 0.3,
        "popularity": 0.2,
        "distance": 0.3,
        "type": 0.2,
    }
    
    total_score = (
        weights["rating"] * score_rating
        + weights["popularity"] * score_popularity
        + weights["distance"] * score_distance
        + weights["type"] * score_type
    )
    
    return total_score

