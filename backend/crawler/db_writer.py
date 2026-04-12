"""
All Supabase writes from the crawler pipeline.

Pipeline roles:
  write_raw_mention()        Step 1 (crawl): save mention with place_id = NULL
  assign_place_to_mention()  Step 2 (resolve): set place_id, create minimal places row
  recompute_boolean_attrs()  Step 2 post-resolve: majority-vote WFH boolean attrs

Key invariants:
  - wfh_score, mention_count, source_count are trigger-owned — never write directly
  - places rows are created here (minimal) or in routers/places.py (enriched)
  - ON CONFLICT DO NOTHING everywhere for idempotent re-runs
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from crawler.article_extractor import MentionExtraction
from crawler.place_resolver import ResolvedPlace
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)


async def ensure_source_exists(
    platform: str,
    handle_or_domain: str,
    is_curated: bool = False,
) -> str:
    """
    UPSERT source ON CONFLICT (platform, handle_or_domain) DO NOTHING, then SELECT id.
    Returns source_id.
    """
    def _query():
        db = get_supabase()
        db.table("sources").upsert(
            {
                "platform": platform,
                "handle_or_domain": handle_or_domain,
                "is_curated": is_curated,
            },
            on_conflict="platform,handle_or_domain",
            ignore_duplicates=True,
        ).execute()
        resp = (
            db.table("sources")
            .select("id")
            .eq("platform", platform)
            .eq("handle_or_domain", handle_or_domain)
            .single()
            .execute()
        )
        return resp.data["id"]

    return await asyncio.to_thread(_query)


async def write_raw_mention(
    url: str,
    source_id: str,
    mention: MentionExtraction,
) -> bool:
    """
    Step 1 (crawl): save a raw mention with place_id = NULL.
    Dedup key: (url, place_name_raw) — same article can mention multiple places,
    but the same article can't mention the same place twice.
    Returns True if inserted (new), False if duplicate.
    """
    def _query():
        db = get_supabase()
        resp = db.table("mentions").upsert(
            {
                "place_id": None,
                "place_name_raw": mention.place_name_raw,
                "source_id": source_id,
                "url": url,
                "evidence_snippet": mention.evidence_snippet,
                "method": "llm",
                "wifi_confidence": mention.wifi_confidence,
                "outlet_confidence": mention.outlet_confidence,
                "quiet_confidence": mention.quiet_confidence,
                "laptop_confidence": mention.laptop_confidence,
            },
            on_conflict="url,place_name_raw",
            ignore_duplicates=True,
        ).execute()
        return len(resp.data) > 0

    return await asyncio.to_thread(_query)


async def assign_place_to_mention(
    mention_id: str,
    resolved: ResolvedPlace,
    region_id: str,
) -> None:
    """
    Step 2 (resolve): assign a Google place_id to a raw mention.

    1. UPSERT a minimal places row (place_id, name, address, lat, lng, region_id)
       — never touches wfh_score (trigger-owned)
    2. UPDATE mentions.place_id = resolved.place_id
       → DB trigger fires → recomputes wfh_score, mention_count, source_count
    """
    def _query():
        db = get_supabase()

        # Step 1: ensure minimal places row exists
        db.table("places").upsert(
            {
                "place_id": resolved.place_id,
                "name": resolved.name,
                "address": resolved.address,
                "lat": resolved.lat,
                "lng": resolved.lng,
                "region_id": region_id,
            },
            on_conflict="place_id",
        ).execute()

        # Step 2: assign place_id to mention → trigger fires
        db.table("mentions").update(
            {"place_id": resolved.place_id}
        ).eq("id", mention_id).execute()

    await asyncio.to_thread(_query)


async def recompute_boolean_attrs_for_region(region_id: str) -> None:
    """
    Majority-vote aggregation of boolean WFH attrs for all places in a region.
    Run after all mentions for the region have been resolved (place_id assigned).

    Majority = >50% of mentions with confidence > 0.5 voting positive.
    noise_level derived from avg_quiet_confidence:
      >= 0.6 → 'quiet'
      0.3–0.6 → 'moderate'
      < 0.3 → 'loud'
    """
    def _query():
        db = get_supabase()
        places_resp = (
            db.table("places").select("place_id").eq("region_id", region_id).execute()
        )
        place_ids = [r["place_id"] for r in places_resp.data]
        if not place_ids:
            return

        for pid in place_ids:
            mentions_resp = (
                db.table("mentions")
                .select("wifi_confidence,outlet_confidence,quiet_confidence,laptop_confidence")
                .eq("place_id", pid)
                .execute()
            )
            rows = mentions_resp.data
            if not rows:
                continue

            def majority(values: list[float]) -> bool | None:
                positive = sum(1 for v in values if v > 0.5)
                total = len(values)
                if total == 0:
                    return None
                return positive > total / 2

            def noise_from_quiet(values: list[float]) -> str | None:
                if not values:
                    return None
                avg = sum(values) / len(values)
                if avg >= 0.6:
                    return "quiet"
                elif avg >= 0.3:
                    return "moderate"
                else:
                    return "loud"

            wifi_vals   = [r["wifi_confidence"]   for r in rows]
            outlet_vals = [r["outlet_confidence"] for r in rows]
            laptop_vals = [r["laptop_confidence"] for r in rows]
            quiet_vals  = [r["quiet_confidence"]  for r in rows]

            update_payload: dict = {
                "has_wifi": majority(wifi_vals),
                "has_outlets": majority(outlet_vals),
                "is_laptop_friendly": majority(laptop_vals),
            }
            nl = noise_from_quiet(quiet_vals)
            if nl is not None:
                update_payload["noise_level"] = nl

            db.table("places").update(update_payload).eq("place_id", pid).execute()

    await asyncio.to_thread(_query)
    logger.info("Recomputed boolean attrs for region %s", region_id)
