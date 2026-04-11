"""
Crawler orchestrator — coordinates all sources in priority order.

Sequence:
  Tavily → Brave → Instagram (sequential, not parallel, to respect
  Google Places Text Search rate limits since all sources feed the
  same place resolver)

Manhattan-only guardrail for Phase 1: raises ValueError for any
city_slug not in ALLOWED_CITY_SLUGS, even for manual /regions/{id}/seed calls.
"""
from __future__ import annotations

import logging

from config import get_settings
from crawler import db_writer, llm_extractor, place_resolver
from crawler.sources import brave_crawler, instagram_crawler, tavily_crawler

logger = logging.getLogger(__name__)

# Hard stop — expand in Phase 2
ALLOWED_CITY_SLUGS = {"nyc-manhattan"}


def _platform_from_url(url: str, crawler_source: str) -> tuple[str, str]:
    """
    Map a URL + crawler source to a valid platform_type enum value and handle_or_domain.
    platform_type enum: reddit | instagram | blog | tiktok | google_review
    """
    lower = url.lower()
    if "reddit.com" in lower:
        return "reddit", "reddit.com"
    if "instagram.com" in lower:
        return "instagram", "instagram.com"
    if "tiktok.com" in lower:
        return "tiktok", "tiktok.com"
    # Everything else (Yelp, blogs, nymag, timeout, etc.) → blog
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
    if city_slug not in ALLOWED_CITY_SLUGS:
        raise ValueError(f"Crawling not enabled for {city_slug} — Phase 2 only")

    settings = get_settings()
    seen_urls: set[str] = set()
    resolve_cache: dict = {}

    logger.info("=" * 60)
    logger.info("CRAWL START: %s (region %s)", city_slug, region_id)
    logger.info("=" * 60)

    # --- Phase 1: Tavily ---
    logger.info("[1/3] Tavily: running %d queries...", len(tavily_crawler.QUERIES_BY_SLUG.get(city_slug, tavily_crawler.MANHATTAN_QUERIES)))
    tavily_mentions = await tavily_crawler.fetch_tavily_mentions(
        city_slug, settings.tavily_api_key, seen_urls=seen_urls
    )
    all_mentions = list(tavily_mentions)
    for m in tavily_mentions:
        seen_urls.add(m.url)
    logger.info("[1/3] Tavily: done — %d unique URLs collected", len(tavily_mentions))

    # --- Phase 2: Brave ---
    logger.info("[2/3] Brave: running queries...")
    brave_mentions = await brave_crawler.fetch_brave_mentions(
        city_slug, settings.brave_search_api_key, seen_urls=seen_urls
    )
    all_mentions.extend(brave_mentions)
    for m in brave_mentions:
        seen_urls.add(m.url)
    logger.info("[2/3] Brave: done — %d new URLs collected", len(brave_mentions))

    # --- Phase 3: Instagram ---
    logger.info("[3/3] Instagram: scraping curated accounts...")
    instagram_mentions = await instagram_crawler.fetch_instagram_mentions()
    all_mentions.extend(instagram_mentions)
    logger.info("[3/3] Instagram: done — %d mentions collected", len(instagram_mentions))

    logger.info("-" * 60)
    logger.info("Total raw mentions: %d — beginning resolve → extract → write", len(all_mentions))
    logger.info("-" * 60)

    # Process each raw mention: resolve → extract → write
    written = 0
    skipped_no_place = 0
    skipped_duplicate = 0

    for i, raw in enumerate(all_mentions, 1):
        try:
            platform, handle_or_domain = _platform_from_url(raw.url, raw.source)
            is_curated = raw.source == "instagram" and platform == "instagram"
            source_id = await db_writer.ensure_source_exists(platform, handle_or_domain, is_curated)

            text_to_resolve = raw.raw_content or raw.snippet
            resolved = await place_resolver.resolve_place(
                raw_text=text_to_resolve,
                location_lat=center_lat,
                location_lng=center_lng,
                api_key=settings.google_places_api_key,
                openai_api_key=settings.openai_api_key,
                similarity_threshold=settings.place_resolver_similarity_threshold,
                distance_threshold_m=settings.place_resolver_distance_threshold_meters,
                _cache=resolve_cache,
            )
            if not resolved:
                # Still extract + save for future pairing (place_id = NULL)
                try:
                    extraction = await llm_extractor.extract_wfh_attributes(
                        raw_text=text_to_resolve,
                        place_name="",
                        openai_api_key=settings.openai_api_key,
                    )
                    await db_writer.write_unmatched_mention(source_id, extraction, raw)
                    skipped_no_place += 1
                    logger.debug("[%d/%d] Unmatched mention saved (place_id=NULL): %s", i, len(all_mentions), raw.url)
                except Exception as unmatched_exc:
                    logger.warning("[%d/%d] Failed to save unmatched mention %s: %s", i, len(all_mentions), raw.url, unmatched_exc)
                    skipped_no_place += 1
                continue

            logger.info("[%d/%d] Resolved → %s | url: %s", i, len(all_mentions), resolved.name, raw.url)

            extraction = await llm_extractor.extract_wfh_attributes(
                raw_text=text_to_resolve,
                place_name=resolved.name,
                openai_api_key=settings.openai_api_key,
            )
            logger.info(
                "  Extract: laptop=%.2f wifi=%.2f outlet=%.2f noise=%.2f",
                extraction.laptop_confidence,
                extraction.wifi_confidence,
                extraction.outlet_confidence,
                extraction.noise_confidence,
            )

            inserted = await db_writer.write_place_and_mention(
                resolved, region_id, source_id, extraction, raw
            )
            if inserted:
                written += 1
                logger.info("  → Written to DB (total written: %d)", written)
            else:
                skipped_duplicate += 1
                logger.debug("  → Duplicate URL, skipped")

        except Exception as exc:
            logger.warning("[%d/%d] Failed to process %s: %s", i, len(all_mentions), raw.url, exc)
            continue

    logger.info("-" * 60)
    logger.info(
        "CRAWL SUMMARY: written=%d  skipped_no_place=%d  skipped_duplicate=%d",
        written, skipped_no_place, skipped_duplicate,
    )

    logger.info("Post-crawl: recomputing boolean attrs for region...")
    await db_writer.recompute_boolean_attrs_for_region(region_id)
    logger.info("=" * 60)
    logger.info("CRAWL COMPLETE: %s", city_slug)
    logger.info("=" * 60)
