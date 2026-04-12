"""
APScheduler cron for weekly re-crawl of stale seeded regions.
Phase 1 optional — MVP uses manual /regions/{id}/seed calls instead.
Started via the lifespan context manager in main.py when uncommented.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def start_scheduler() -> None:
    """
    Start the APScheduler background scheduler.
    Uncomment and wire into main.py lifespan when ready for Phase 2.
    """
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not installed — weekly re-crawl disabled.")
        return

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        _recrawl_stale_regions,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="weekly_recrawl",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("APScheduler started — weekly re-crawl scheduled for Sunday 02:00 UTC.")


async def _recrawl_stale_regions() -> None:
    """Re-crawl all seeded regions to refresh data."""
    from services import supabase_client
    from background.seed_job import trigger_seed

    regions = await supabase_client.list_all_regions()
    seeded = [r for r in regions if r["status"] == "seeded"]

    logger.info("Weekly re-crawl: found %d seeded regions to refresh.", len(seeded))

    for region in seeded:
        # Reset to cold so trigger_seed can claim it
        await supabase_client.set_region_status(region["id"], "cold")
        await trigger_seed(region["id"])
