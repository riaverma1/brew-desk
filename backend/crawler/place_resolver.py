"""
Resolves free-text place mention → canonical Google place_id.

Sequence:
  1. gpt-4o-mini extracts place name from raw_text
  2. Google Places Text Search with location bias
  3. difflib.SequenceMatcher similarity > threshold AND haversine distance < threshold
  4. Return best match or None

Cache resolved place_ids in-memory per crawl run (keyed by place_name).
"""
from __future__ import annotations

import difflib
import json
import logging
import math
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from services.google_places import text_search

logger = logging.getLogger(__name__)

# Single shared client — one connection pool for the whole crawl run
_openai_client: AsyncOpenAI | None = None


def get_openai_client(api_key: str) -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=api_key, timeout=30.0)
    return _openai_client


@dataclass
class ResolvedPlace:
    place_id: str
    name: str
    lat: float
    lng: float
    address: str


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def resolve_place(
    raw_text: str,
    location_lat: float,
    location_lng: float,
    api_key: str,
    openai_api_key: str,
    similarity_threshold: float = 0.65,
    distance_threshold_m: int = 300,
    _cache: dict | None = None,
) -> ResolvedPlace | None:
    """
    Resolve a raw text mention to a canonical Google place_id.
    Pass _cache dict across multiple calls within one crawl run to avoid
    re-resolving the same cafe mentioned in many posts.
    """
    if not raw_text or not raw_text.strip():
        return None

    # Step 1: extract place name via gpt-4o-mini (cheap, JSON output, 30s timeout)
    logger.info("  Resolver: calling OpenAI to extract place name...")
    client = get_openai_client(openai_api_key)
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract the coffee shop or cafe name from the text. "
                        'Return JSON: {"place_name": "<name>" | null}'
                    ),
                },
                {"role": "user", "content": raw_text[:800]},
            ],
        )
        result = json.loads(response.choices[0].message.content or "{}")
        place_name: str | None = result.get("place_name")
    except Exception as exc:
        logger.warning("  Resolver: place name extraction failed: %s", exc)
        return None

    if not place_name:
        logger.info("  Resolver: no place name found in text, skipping")
        return None

    logger.debug("  Resolver: extracted place name %r", place_name)

    # Check in-run cache
    if _cache is not None and place_name in _cache:
        cached = _cache[place_name]
        logger.debug("  Resolver: cache hit for %r → %s", place_name, cached.name if cached else "None")
        return cached

    # Step 2: Google Places Text Search with location bias
    logger.info("  Resolver: searching Google Places for %r...", place_name)
    query = f"{place_name} cafe coffee NYC"
    location_bias = {
        "circle": {
            "center": {"latitude": location_lat, "longitude": location_lng},
            "radius": 10000.0,
        }
    }
    candidates = await text_search(query, location_bias, api_key)

    # Retry without location bias for well-known chains if no results
    if not candidates:
        candidates = await text_search(f"{place_name} NYC", {}, api_key)

    # Step 3: fuzzy match by name similarity + haversine distance.
    # 25km covers all of Manhattan/NYC — just a loose "is this in our city" guard.
    effective_distance_threshold = max(distance_threshold_m, 25_000)

    best: ResolvedPlace | None = None
    best_sim = 0.0

    # First word of the query — almost always the most distinctive token
    # (e.g. "Flop" in "Flop House", "Blue" in "Blue Bottle")
    query_first_word = place_name.lower().split()[0] if place_name.split() else place_name.lower()

    for candidate in candidates:
        sim = difflib.SequenceMatcher(None, place_name.lower(), candidate["name"].lower()).ratio()
        if sim < similarity_threshold:
            continue

        # Guard: first word must bear some resemblance to the candidate's first word.
        # Prevents "Flop House" → "Lava House" (sim 0.667 passes threshold but
        # first-word sim "flop"/"lava" = 0.0, well below 0.5).
        candidate_first_word = candidate["name"].lower().split()[0] if candidate["name"].split() else ""
        first_word_sim = difflib.SequenceMatcher(None, query_first_word, candidate_first_word).ratio()
        if first_word_sim < 0.5:
            logger.debug(
                "  Resolver: rejected %r → %r (overall sim=%.2f OK but first-word sim=%.2f too low)",
                place_name, candidate["name"], sim, first_word_sim,
            )
            continue

        lat2, lng2 = candidate.get("lat"), candidate.get("lng")
        if lat2 is None or lng2 is None:
            continue
        dist = _haversine_meters(location_lat, location_lng, lat2, lng2)
        if dist > effective_distance_threshold:
            continue
        if sim > best_sim:
            best_sim = sim
            best = ResolvedPlace(
                place_id=candidate["place_id"],
                name=candidate["name"],
                lat=lat2,
                lng=lng2,
                address=candidate.get("formatted_address", ""),
            )

    if best:
        logger.debug("  Resolver: matched %r → %s (sim=%.2f)", place_name, best.name, best_sim)
    else:
        logger.debug("  Resolver: no match for %r among %d candidates", place_name, len(candidates))

    if _cache is not None:
        _cache[place_name] = best

    return best
