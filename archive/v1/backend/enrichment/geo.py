import math
from typing import Dict, List, Optional, Tuple

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