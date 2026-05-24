"""
Crawler orchestrator — Step 1 of the pipeline.

Responsibility: collect articles from all sources, run the LLM extractor on
each article to produce individual mention rows, and save them to the DB with
place_id = NULL. Resolution (Step 2) happens separately in resolver_job.py.

Sources run in priority order:
  Tavily → Brave → Instagram (sequential to respect rate limits)

Manhattan-only guardrail for Phase 1.
"""
from __future__ import annotations

import logging

from config import get_settings
from crawler import article_extractor, db_writer
from crawler.sources import brave_crawler, instagram_crawler, tavily_crawler

logger = logging.getLogger(__name__)

ALLOWED_CITY_SLUGS = {
    "nyc-manhattan",
    "nyc-queens",
    "nyc-brooklyn",
    "chicago",
    "phoenix",
    "albuquerque",
}


def _platform_from_url(url: str, crawler_source: str) -> tuple[str, str]:
    """
    Map a URL + crawler source to (platform_type enum value, handle_or_domain).
    platform_type: reddit | instagram | blog | tiktok | google_review
    """
    lower = url.lower()
    if "reddit.com" in lower:
        return "reddit", "reddit.com"
    if "instagram.com" in lower:
        return "instagram", "instagram.com"
    if "tiktok.com" in lower:
        return "tiktok", "tiktok.com"
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lstrip("www.")
    except Exception:
        domain = "unknown"
    return "blog", domain


async def run_for_region(
    region_id: str,
    center_lat: float,
    center_lng: float,
    city_slug: str,
) -> None:
    """
    Crawl all sources for the given region and save raw mentions (place_id=NULL).
    Does NOT resolve place names or create places rows — that is Step 2.
    """
    if city_slug not in ALLOWED_CITY_SLUGS:
        raise ValueError(f"Crawling not enabled for {city_slug} — Phase 2 only")

    settings = get_settings()
    seen_urls: set[str] = set()

    logger.info("=" * 60)
    logger.info("CRAWL START (Step 1): %s  region=%s", city_slug, region_id)
    logger.info("=" * 60)

    # --- Tavily ---
    logger.info("[1/3] Tavily: running queries...")
    tavily_mentions = await tavily_crawler.fetch_tavily_mentions(
        city_slug, settings.tavily_api_key, seen_urls=seen_urls
    )
    all_raw = list(tavily_mentions)
    for m in tavily_mentions:
        seen_urls.add(m.url)
    logger.info("[1/3] Tavily: %d unique URLs", len(tavily_mentions))

    # --- Brave ---
    logger.info("[2/3] Brave: running queries...")
    brave_mentions = await brave_crawler.fetch_brave_mentions(
        city_slug, settings.brave_search_api_key, seen_urls=seen_urls
    )
    all_raw.extend(brave_mentions)
    for m in brave_mentions:
        seen_urls.add(m.url)
    logger.info("[2/3] Brave: %d new URLs", len(brave_mentions))

    # --- Instagram ---
    logger.info("[3/3] Instagram: scraping curated accounts...")
    instagram_mentions = await instagram_crawler.fetch_instagram_mentions()
    all_raw.extend(instagram_mentions)
    logger.info("[3/3] Instagram: %d mentions", len(instagram_mentions))

    logger.info("-" * 60)
    logger.info("Total articles: %d — extracting mentions...", len(all_raw))
    logger.info("-" * 60)

    written = 0
    skipped_no_mentions = 0
    skipped_duplicate = 0

    for i, raw in enumerate(all_raw, 1):
        try:
            platform, handle_or_domain = _platform_from_url(raw.url, raw.source)
            is_curated = raw.source == "instagram" and platform == "instagram"
            source_id = await db_writer.ensure_source_exists(
                platform, handle_or_domain, is_curated
            )

            text = raw.raw_content or raw.snippet
            mentions = await article_extractor.extract_all_mentions(
                text, settings.openai_api_key
            )

            if not mentions:
                skipped_no_mentions += 1
                logger.debug("[%d/%d] No named places found: %s", i, len(all_raw), raw.url)
                continue

            logger.info(
                "[%d/%d] %d mention(s) extracted from %s",
                i, len(all_raw), len(mentions), raw.url,
            )

            for mention in mentions:
                inserted = await db_writer.write_raw_mention(
                    raw.url, source_id, mention, source_title=raw.source_title
                )
                if inserted:
                    written += 1
                    logger.debug(
                        "  → Saved: %r  laptop=%.2f wifi=%.2f outlet=%.2f quiet=%.2f",
                        mention.place_name_raw,
                        mention.laptop_confidence,
                        mention.wifi_confidence,
                        mention.outlet_confidence,
                        mention.quiet_confidence,
                    )
                else:
                    skipped_duplicate += 1

        except Exception as exc:
            logger.warning("[%d/%d] Failed to process %s: %s", i, len(all_raw), raw.url, exc)
            continue

    logger.info("-" * 60)
    logger.info(
        "CRAWL COMPLETE: written=%d  skipped_no_mentions=%d  skipped_duplicate=%d",
        written, skipped_no_mentions, skipped_duplicate,
    )
    logger.info("All mentions saved with place_id=NULL — run resolver_job to resolve.")
    logger.info("=" * 60)
