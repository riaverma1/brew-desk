"""
All Supabase writes from the crawler: places, mentions, sources.
Post-crawl boolean attr recomputation via SQL conditional aggregation.

Key constraints:
- UPSERT places must NOT overwrite wfh_score (trigger-owned)
- ensure_source_exists uses ON CONFLICT DO NOTHING (concurrent crawlers race here)
- recompute_boolean_attrs uses SQL aggregation — never Python-side row pulling
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from crawler.llm_extractor import ExtractionResult
from crawler.place_resolver import ResolvedPlace
from crawler.sources.tavily_crawler import RawMention
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)


async def ensure_source_exists(
    platform: str,
    handle_or_domain: str,
    is_curated: bool = False,
) -> str:
    """
    UPSERT source row ON CONFLICT (platform, handle_or_domain) DO NOTHING,
    then SELECT id. Returns source_id.
    """
    def _query():
        db = get_supabase()
        db.table("sources").upsert(
            {"platform": platform, "handle_or_domain": handle_or_domain, "is_curated": is_curated},
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


async def write_place_and_mention(
    resolved: ResolvedPlace,
    region_id: str,
    source_id: str,
    extraction: ExtractionResult,
    raw_mention: RawMention,
) -> bool:
    """
    1. UPSERT places ON CONFLICT (place_id) — does NOT touch wfh_score
    2. INSERT INTO mentions ON CONFLICT (url) DO NOTHING
       → DB trigger fires: recomputes wfh_score, mention_count, source_count
    Returns True if mention was inserted (new), False if duplicate.
    """
    def _query():
        db = get_supabase()

        # Step 1: upsert place (never overwrite wfh_score)
        db.table("places").upsert(
            {
                "place_id": resolved.place_id,
                "name": resolved.name,
                "address": resolved.address,
                "lat": resolved.lat,
                "lng": resolved.lng,
                "region_id": region_id,
                "last_enriched_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="place_id",
        ).execute()

        # Step 2: insert mention ON CONFLICT DO NOTHING
        # place_name_raw='' marks this as an original single-crawl row
        resp = db.table("mentions").upsert(
            {
                "place_id": resolved.place_id,
                "source_id": source_id,
                "url": raw_mention.url,
                "place_name_raw": "",
                "evidence_snippet": extraction.evidence_snippet,
                "method": "llm",
                "wifi_confidence": extraction.wifi_confidence,
                "outlet_confidence": extraction.outlet_confidence,
                "noise_confidence": extraction.noise_confidence,
                "laptop_confidence": extraction.laptop_confidence,
            },
            on_conflict="url,place_name_raw",
            ignore_duplicates=True,
        ).execute()

        return len(resp.data) > 0

    return await asyncio.to_thread(_query)


async def write_multi_mention(
    resolved: ResolvedPlace,
    region_id: str | None,
    source_id: str,
    extraction: ExtractionResult,
    url: str,
    place_name_raw: str,
) -> bool:
    """
    Write a single resolved place from a multi-mention source (Reddit thread,
    blog list, etc.). place_name_raw is the lowercased extracted place name —
    used as the secondary dedup key so multiple places can share the same URL.

    1. UPSERT places ON CONFLICT (place_id)
    2. INSERT INTO mentions ON CONFLICT (url, place_name_raw) DO NOTHING
    Returns True if mention was inserted (new), False if duplicate.
    """
    def _query():
        db = get_supabase()

        place_data: dict = {
            "place_id": resolved.place_id,
            "name": resolved.name,
            "address": resolved.address,
            "lat": resolved.lat,
            "lng": resolved.lng,
            "last_enriched_at": datetime.now(timezone.utc).isoformat(),
        }
        # Only set region_id if provided — avoids overwriting an existing region
        # with NULL when called from the retroactive matcher without a region context
        if region_id:
            place_data["region_id"] = region_id

        db.table("places").upsert(place_data, on_conflict="place_id").execute()

        resp = db.table("mentions").upsert(
            {
                "place_id": resolved.place_id,
                "source_id": source_id,
                "url": url,
                "place_name_raw": place_name_raw,
                "evidence_snippet": extraction.evidence_snippet,
                "method": "llm",
                "wifi_confidence": extraction.wifi_confidence,
                "outlet_confidence": extraction.outlet_confidence,
                "noise_confidence": extraction.noise_confidence,
                "laptop_confidence": extraction.laptop_confidence,
            },
            on_conflict="url,place_name_raw",
            ignore_duplicates=True,
        ).execute()

        return len(resp.data) > 0

    return await asyncio.to_thread(_query)


async def mark_mention_multi_processed(mention_id: str) -> None:
    """Set is_multi_processed=TRUE on the original crawl row after retroactive processing."""
    def _query():
        db = get_supabase()
        db.table("mentions").update({"is_multi_processed": True}).eq("id", mention_id).execute()

    await asyncio.to_thread(_query)


async def write_unmatched_mention(
    source_id: str,
    extraction: ExtractionResult,
    raw_mention: RawMention,
) -> bool:
    """
    Save a mention with place_id = NULL when place resolver found no match.
    Allows future pairing when new regions are seeded.
    INSERT ON CONFLICT (url, place_name_raw) DO NOTHING — returns True if newly inserted.
    """
    def _query():
        db = get_supabase()
        resp = db.table("mentions").upsert(
            {
                "place_id": None,
                "source_id": source_id,
                "url": raw_mention.url,
                "place_name_raw": "",
                "evidence_snippet": extraction.evidence_snippet,
                "method": "llm",
                "wifi_confidence": extraction.wifi_confidence,
                "outlet_confidence": extraction.outlet_confidence,
                "noise_confidence": extraction.noise_confidence,
                "laptop_confidence": extraction.laptop_confidence,
            },
            on_conflict="url,place_name_raw",
            ignore_duplicates=True,
        ).execute()
        return len(resp.data) > 0

    return await asyncio.to_thread(_query)


async def recompute_boolean_attrs_for_region(region_id: str) -> None:
    """
    Majority-vote aggregation of boolean WFH attrs for all places in a region.
    Uses SQL conditional aggregation — does NOT pull rows to Python.
    A majority is defined as >50% of mentions with confidence > 0.5 voting True.
    """
    def _query():
        db = get_supabase()
        # Fetch place_ids in this region
        places_resp = db.table("places").select("place_id").eq("region_id", region_id).execute()
        place_ids = [r["place_id"] for r in places_resp.data]
        if not place_ids:
            return

        for pid in place_ids:
            mentions_resp = (
                db.table("mentions")
                .select("wifi_confidence,outlet_confidence,noise_confidence,laptop_confidence")
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

            def noise_vote(values: list[float]) -> str | None:
                # Map confidence to noise level: low confidence → quiet, high → loud
                # noise_confidence > 0.6 → loud, 0.3-0.6 → moderate, < 0.3 → quiet
                if not values:
                    return None
                avg = sum(values) / len(values)
                if avg >= 0.6:
                    return "loud"
                elif avg >= 0.3:
                    return "moderate"
                else:
                    return "quiet"

            wifi_vals = [r["wifi_confidence"] for r in rows]
            outlet_vals = [r["outlet_confidence"] for r in rows]
            laptop_vals = [r["laptop_confidence"] for r in rows]
            noise_vals = [r["noise_confidence"] for r in rows]

            update_payload: dict = {
                "has_wifi": majority(wifi_vals),
                "has_outlets": majority(outlet_vals),
                "is_laptop_friendly": majority(laptop_vals),
            }
            nl = noise_vote(noise_vals)
            if nl is not None:
                update_payload["noise_level"] = nl

            db.table("places").update(update_payload).eq("place_id", pid).execute()

    await asyncio.to_thread(_query)
    logger.info("Recomputed boolean attrs for region %s", region_id)
