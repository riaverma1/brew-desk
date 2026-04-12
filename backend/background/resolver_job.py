"""
Resolver job — Step 2 of the pipeline.

Two modes:

  Streaming (used by seed_job):
    resolve_streaming(region_id, center_lat, center_lng, crawl_done)
    Polls for newly written unresolved mentions every POLL_INTERVAL_SECS while
    the crawler is still running. When crawl_done event fires, does one final
    pass to catch mentions written in the last interval, then runs boolean attrs.
    This runs concurrently with the crawler so the first resolved pins appear
    ~30s into the crawl rather than after it fully completes.

  Single-pass (used by admin /regions/resolve route):
    resolve_for_region(region_id, center_lat, center_lng)
    One pass over all unresolved mentions, then boolean attrs. Useful for
    re-running after failures.

Rate limiting: GOOGLE_API_DELAY between Text Search calls.
"""
from __future__ import annotations

import asyncio
import logging

from config import get_settings
from crawler import db_writer
from crawler.place_resolver import ResolvedPlace, resolve_place
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_GOOGLE_API_DELAY = 0.3    # seconds between Google Text Search calls
POLL_INTERVAL_SECS = 30    # how often streaming resolver polls for new mentions


async def _fetch_unresolved_mentions() -> list[dict]:
    """Fetch all mentions with place_id IS NULL."""
    def _query():
        db = get_supabase()
        return (
            db.table("mentions")
            .select("id, place_name_raw")
            .is_("place_id", "null")
            .execute()
            .data
        )
    return await asyncio.to_thread(_query)


async def _resolve_batch(
    region_id: str,
    center_lat: float,
    center_lng: float,
    resolve_cache: dict,
) -> dict:
    """
    One pass: resolve all currently unresolved mentions and assign place_ids.
    Does NOT recompute boolean attrs — that only happens at the very end.
    Returns {"resolved": N, "skipped": M}.

    Uses resolve_cache shared across calls within a seed run so the same
    cafe name is never looked up more than once via Google Text Search.
    """
    settings = get_settings()
    unresolved = await _fetch_unresolved_mentions()

    if not unresolved:
        return {"resolved": 0, "skipped": 0}

    resolved_count = 0
    skipped_count = 0

    for row in unresolved:
        mention_id = row["id"]
        place_name = row["place_name_raw"].strip()

        if not place_name:
            skipped_count += 1
            continue

        try:
            resolved: ResolvedPlace | None = await resolve_place(
                raw_text=place_name,
                location_lat=center_lat,
                location_lng=center_lng,
                api_key=settings.google_places_api_key,
                openai_api_key=settings.openai_api_key,
                similarity_threshold=settings.place_resolver_similarity_threshold,
                distance_threshold_m=settings.place_resolver_distance_threshold_meters,
                _cache=resolve_cache,
            )

            if resolved:
                await db_writer.assign_place_to_mention(mention_id, resolved, region_id)
                resolved_count += 1
                logger.info("Resolved %r → %s (%s)", place_name, resolved.name, resolved.place_id)
            else:
                skipped_count += 1
                logger.debug("No match for %r", place_name)

        except Exception as exc:
            skipped_count += 1
            logger.warning("Failed to resolve %r: %s", place_name, exc)

        await asyncio.sleep(_GOOGLE_API_DELAY)

    return {"resolved": resolved_count, "skipped": skipped_count}


async def resolve_streaming(
    region_id: str,
    center_lat: float,
    center_lng: float,
    crawl_done: asyncio.Event,
) -> dict:
    """
    Streaming resolver: polls for new unresolved mentions every POLL_INTERVAL_SECS
    while the crawler is running, then does a final pass once crawl_done fires.

    Timeline (approximate, with 30s poll interval):
      t=0s   crawler starts writing mentions
      t=30s  first resolver batch — resolves whatever is written so far → pins appear
      t=60s  second batch, picks up mentions written in last 30s
      ...
      t=Ns   crawl completes → crawl_done is set
      t=Ns   resolver does final pass to catch any stragglers
      t=Ns   boolean attr recompute runs
    """
    resolve_cache: dict = {}
    total_resolved = 0
    total_skipped = 0
    poll = 0

    logger.info("Resolver streaming: started for region %s (poll every %ds)", region_id, POLL_INTERVAL_SECS)

    while True:
        # Wait for poll interval OR crawl completion, whichever comes first
        try:
            await asyncio.wait_for(crawl_done.wait(), timeout=POLL_INTERVAL_SECS)
            # crawl_done fired before timeout — exit the poll loop
            logger.info("Resolver streaming: crawl_done received, exiting poll loop")
            break
        except asyncio.TimeoutError:
            pass  # Normal — poll interval elapsed, do another batch

        poll += 1
        logger.info("Resolver streaming: poll #%d for region %s", poll, region_id)
        result = await _resolve_batch(region_id, center_lat, center_lng, resolve_cache)
        total_resolved += result["resolved"]
        total_skipped += result["skipped"]
        logger.info(
            "Resolver streaming: poll #%d done — resolved=%d skipped=%d (cumulative: %d/%d)",
            poll, result["resolved"], result["skipped"], total_resolved, total_skipped,
        )

    # Final pass: catch mentions written after the last poll (or all of them if crawl
    # finished before the first poll interval elapsed)
    logger.info("Resolver streaming: final pass...")
    result = await _resolve_batch(region_id, center_lat, center_lng, resolve_cache)
    total_resolved += result["resolved"]
    total_skipped += result["skipped"]
    logger.info(
        "Resolver streaming: final pass done — resolved=%d skipped=%d",
        result["resolved"], result["skipped"],
    )

    # Boolean attrs only once, after all mentions are resolved
    logger.info("Resolver streaming: recomputing boolean attrs for region %s", region_id)
    await db_writer.recompute_boolean_attrs_for_region(region_id)

    summary = {"resolved": total_resolved, "skipped": total_skipped, "polls": poll + 1}
    logger.info("Resolver streaming complete: %s", summary)
    return summary


async def resolve_for_region(
    region_id: str,
    center_lat: float,
    center_lng: float,
) -> dict:
    """
    Single-pass resolver for admin/manual use (e.g. POST /regions/resolve).
    Resolves all currently unresolved mentions in one shot, then recomputes
    boolean attrs. Does not poll.
    """
    resolve_cache: dict = {}
    logger.info("Resolver single-pass: starting for region %s", region_id)

    result = await _resolve_batch(region_id, center_lat, center_lng, resolve_cache)

    logger.info("Resolver single-pass: recomputing boolean attrs for region %s", region_id)
    await db_writer.recompute_boolean_attrs_for_region(region_id)

    logger.info("Resolver single-pass complete: %s", result)
    return result
