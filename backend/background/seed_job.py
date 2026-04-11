"""
Entry point for seeding a cold region. Called via FastAPI BackgroundTasks
or manually via the /regions/{id}/seed admin route.

Sequence:
  1. Conditional UPDATE cold→crawling (idempotency lock — 0 rows = already claimed)
  2. run crawler orchestrator
  3. Mark region as seeded
  4. On exception: roll back to cold so next pan can retry
"""
from __future__ import annotations

import asyncio
import logging

from services import supabase_client

logger = logging.getLogger(__name__)


async def trigger_seed(region_id: str) -> None:
    # Step 1: atomically claim the region (TOCTOU-safe)
    claimed = await supabase_client.claim_region_for_crawl(region_id)
    if not claimed:
        logger.info("Region %s already claimed by another worker — aborting.", region_id)
        return

    logger.info("Seed job started for region %s", region_id)

    try:
        # Fetch region details needed by the orchestrator
        regions = await supabase_client.list_all_regions()
        region = next((r for r in regions if r["id"] == region_id), None)
        if not region:
            raise ValueError(f"Region {region_id} not found")

        center_lat = (region["min_lat"] + region["max_lat"]) / 2
        center_lng = (region["min_lng"] + region["max_lng"]) / 2
        city_slug = region["city_slug"]

        # Step 2: run crawler
        from crawler.orchestrator import run_for_region

        await run_for_region(
            region_id=region_id,
            center_lat=center_lat,
            center_lng=center_lng,
            city_slug=city_slug,
        )

        # Step 3: mark seeded
        from datetime import datetime, timezone

        db = supabase_client.get_supabase()
        db.table("regions").update(
            {"status": "seeded", "last_crawled_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", region_id).execute()

        logger.info("Seed job completed for region %s", region_id)

    except Exception as exc:
        logger.exception("Seed job failed for region %s: %s", region_id, exc)
        # Step 4: roll back to cold so next map pan can retry
        try:
            await supabase_client.set_region_status(region_id, "cold")
        except Exception as rollback_exc:
            logger.error("Failed to roll back region %s to cold: %s", region_id, rollback_exc)
