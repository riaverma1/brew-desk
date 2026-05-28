"""
Entry point for seeding a cold region. Called via FastAPI BackgroundTasks
or manually via the /regions/{id}/seed admin route.

Sequence:
  1. Conditional UPDATE cold→crawling (idempotency lock)
  2. Launch crawler (Step 1) and streaming resolver (Step 2) CONCURRENTLY
       - Crawler writes raw mentions (place_id=NULL)
       - Resolver polls every 30s, assigns place_ids as mentions come in
       - First pins appear ~30s into the crawl, not after it finishes
  3. Crawl finishes → signal crawl_done event
  4. Resolver does final pass + boolean attr recompute
  5. Mark region as seeded
  6. On exception: roll back to cold so next pan can retry
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from services import supabase_client

logger = logging.getLogger(__name__)


async def trigger_seed(region_id: str) -> None:
    # Step 1: atomically claim the region (TOCTOU-safe)
    claimed = await supabase_client.claim_region_for_crawl(region_id)
    if not claimed:
        logger.info("Region %s already claimed — aborting.", region_id)
        return

    logger.info("Seed job started for region %s", region_id)

    try:
        regions = await supabase_client.list_all_regions()
        region = next((r for r in regions if r["id"] == region_id), None)
        if not region:
            raise ValueError(f"Region {region_id} not found")

        center_lat = (region["min_lat"] + region["max_lat"]) / 2
        center_lng = (region["min_lng"] + region["max_lng"]) / 2
        city_slug = region["city_slug"]

        from crawler.orchestrator import run_for_region
        from background.resolver_job import resolve_streaming

        # Event signals the resolver when the crawl has finished writing mentions
        crawl_done = asyncio.Event()

        async def _crawl():
            await run_for_region(
                region_id=region_id,
                center_lat=center_lat,
                center_lng=center_lng,
                city_slug=city_slug,
            )
            logger.info("Seed job: crawl complete — signalling resolver")
            crawl_done.set()

        # Step 2: run crawler and resolver concurrently.
        # Crawler writes raw mentions; resolver picks them up every 30s.
        crawl_task = asyncio.create_task(_crawl())
        resolve_task = asyncio.create_task(
            resolve_streaming(region_id, center_lat, center_lng, crawl_done)
        )

        # Wait for crawl to finish (or fail)
        try:
            await crawl_task
        except Exception as crawl_exc:
            # Crawl failed — cancel the resolver, surface the error
            resolve_task.cancel()
            try:
                await resolve_task
            except (asyncio.CancelledError, Exception):
                pass
            raise crawl_exc

        # Crawl succeeded — wait for resolver to finish its final pass
        try:
            summary = await resolve_task
            logger.info("Seed job: resolver complete — %s", summary)
        except Exception as resolve_exc:
            # Resolver failure is isolated — region still gets seeded
            logger.warning(
                "Seed job: resolver failed for region %s: %s — proceeding to seeded",
                region_id, resolve_exc,
            )

        # Step 3: enrich new places (photos, rating, hours) — isolated, non-blocking
        try:
            from background.enrich_job import enrich_unenriched_places
            from config import get_settings
            enrich_summary = await enrich_unenriched_places(region_id, get_settings().google_places_api_key)
            logger.info("Seed job: enrich complete — %s", enrich_summary)
        except Exception as enrich_exc:
            logger.warning("Seed job: enrich failed for region %s: %s — proceeding to seeded", region_id, enrich_exc)

        # Step 4: mark seeded
        db = supabase_client.get_supabase()
        db.table("regions").update(
            {"status": "seeded", "last_crawled_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", region_id).execute()

        logger.info("Seed job completed for region %s", region_id)

    except Exception as exc:
        logger.exception("Seed job failed for region %s: %s", region_id, exc)
        try:
            await supabase_client.set_region_status(region_id, "cold")
        except Exception as rollback_exc:
            logger.error("Failed to roll back region %s to cold: %s", region_id, rollback_exc)
