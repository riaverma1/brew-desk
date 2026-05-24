"""
Singleton supabase-py wrapper with typed async query helpers.

supabase-py v2 is synchronous; calls are wrapped in asyncio.to_thread
to avoid blocking the FastAPI event loop.
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from supabase import Client, create_client

from config import get_settings
from models.place import MapBounds

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


async def get_places_by_ids(
    place_ids: list[str],
    score_threshold: float,
    laptop_confidence_threshold: float,
) -> list[dict]:
    """
    Return enriched places filtered by score and laptop confidence thresholds.
    When thresholds are 0 all DB-matched places are returned directly.
    """
    if not place_ids:
        return []

    def _query():
        db = get_supabase()

        if laptop_confidence_threshold > 0:
            # Subquery: only place_ids with a sufficiently confident mention
            mentions_resp = (
                db.table("mentions")
                .select("place_id")
                .in_("place_id", place_ids)
                .gte("laptop_confidence", laptop_confidence_threshold)
                .execute()
            )
            eligible_ids = list({row["place_id"] for row in mentions_resp.data if row["place_id"]})
            if not eligible_ids:
                return []
        else:
            eligible_ids = place_ids

        query = db.table("places").select("*").in_("place_id", eligible_ids)
        if score_threshold > 0:
            query = query.gte("wfh_score", score_threshold)
        return query.execute().data

    return await asyncio.to_thread(_query)


async def get_places_in_bounds(bounds: MapBounds) -> list[dict]:
    """
    Return all places within viewport lat/lng bounds.
    No filters — every row in the places table is a resolver-created, vetted place.
    Used for diagnostics and admin tooling; the hot path uses get_places_by_ids.
    """
    def _query():
        db = get_supabase()
        return (
            db.table("places")
            .select("*")
            .gte("lat", bounds.south)
            .lte("lat", bounds.north)
            .gte("lng", bounds.west)
            .lte("lng", bounds.east)
            .execute()
            .data
        )
    return await asyncio.to_thread(_query)


async def save_google_place_data(place_id: str, data: dict) -> None:
    """Save Google Places fields (photos, rating, type, hours) — best-effort background task."""
    if not data:
        return

    def _query():
        db = get_supabase()
        db.table("places").update(data).eq("place_id", place_id).execute()

    await asyncio.to_thread(_query)


async def get_mentions_for_place(place_id: str) -> list[dict]:
    """
    Return mentions with source platform/handle joined, ordered by laptop_confidence desc.
    Limited to 20 as Phase 1 safety valve.
    """
    def _query():
        db = get_supabase()
        resp = (
            db.table("mentions")
            .select("id, url, evidence_snippet, laptop_confidence, mentioned_at, source_title, sources(platform, handle_or_domain)")
            .eq("place_id", place_id)
            .order("laptop_confidence", desc=True)
            .limit(20)
            .execute()
        )
        return resp.data

    return await asyncio.to_thread(_query)


async def get_overlapping_regions(bounds: MapBounds) -> list[dict]:
    """Return all regions whose bounding boxes overlap the given viewport."""
    def _query():
        db = get_supabase()
        resp = (
            db.table("regions")
            .select("*")
            .lte("min_lat", bounds.north)
            .gte("max_lat", bounds.south)
            .lte("min_lng", bounds.east)
            .gte("max_lng", bounds.west)
            .execute()
        )
        return resp.data

    return await asyncio.to_thread(_query)


async def set_region_status(region_id: str, status: str) -> None:
    def _query():
        db = get_supabase()
        db.table("regions").update({"status": status}).eq("id", region_id).execute()

    await asyncio.to_thread(_query)


async def claim_region_for_crawl(region_id: str) -> bool:
    """
    Atomically flip status cold→crawling. Returns True if this caller claimed it.
    Uses conditional UPDATE to prevent TOCTOU race.
    """
    def _query():
        db = get_supabase()
        resp = (
            db.table("regions")
            .update({"status": "crawling"})
            .eq("id", region_id)
            .eq("status", "cold")
            .execute()
        )
        return len(resp.data) > 0

    return await asyncio.to_thread(_query)


async def upsert_place(place_data: dict) -> None:
    """UPSERT a place row. Does NOT touch wfh_score — trigger-owned."""
    def _query():
        db = get_supabase()
        db.table("places").upsert(place_data, on_conflict="place_id").execute()

    await asyncio.to_thread(_query)


async def insert_mention_if_new(mention_data: dict) -> bool:
    """
    INSERT mention ON CONFLICT (url) DO NOTHING.
    Returns True if the row was inserted (new), False if it already existed.
    """
    def _query():
        db = get_supabase()
        resp = (
            db.table("mentions")
            .upsert(mention_data, on_conflict="url", ignore_duplicates=True)
            .execute()
        )
        return len(resp.data) > 0

    return await asyncio.to_thread(_query)


async def get_unenriched_places(region_id: str | None = None) -> list[dict]:
    """
    Return places that have never been enriched with Google data (last_enriched_at IS NULL).
    Optionally filtered to a specific region. Returns only place_id column.
    """
    def _query():
        db = get_supabase()
        q = db.table("places").select("place_id").is_("last_enriched_at", "null")
        if region_id:
            q = q.eq("region_id", region_id)
        return q.execute().data

    return await asyncio.to_thread(_query)


async def get_all_places_in_region(region_id: str) -> list[dict]:
    """Return all places in a region regardless of enrichment status. Returns only place_id."""
    def _query():
        db = get_supabase()
        return db.table("places").select("place_id").eq("region_id", region_id).execute().data

    return await asyncio.to_thread(_query)


async def list_all_regions() -> list[dict]:
    def _query():
        db = get_supabase()
        return db.table("regions").select("*").execute().data

    return await asyncio.to_thread(_query)
