"""
Retroactive multi-mention resolver.

Picks up original crawl rows (place_name_raw='', is_multi_processed=FALSE) —
both unmatched (place_id=NULL) and single-matched — re-fetches the URL content,
extracts ALL named cafes via multi_mention_extractor, resolves each to a Google
place_id, and writes new mention rows per place.

After processing a URL (success or no places found), the original row is marked
is_multi_processed=TRUE so it is never reprocessed.

Entry points:
  - run_retroactive_match(since=<timestamp>) — called from seed_job after crawl,
    scoped to mentions created during that crawl run only.
  - run_retroactive_match(since=None) — called from the admin endpoint,
    processes ALL unprocessed rows globally.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# Reddit JSON API: append to any thread URL
_REDDIT_JSON_SUFFIX = ".json?limit=100&raw_json=1"
_FETCH_TIMEOUT = 10  # seconds
_INTER_URL_DELAY = 0.5  # seconds — courtesy rate limiting


def _is_reddit_url(url: str) -> bool:
    return "reddit.com" in url.lower()


async def _fetch_reddit_text(url: str) -> str:
    """
    Fetch a Reddit thread via the JSON API and concatenate the selftext +
    all comment bodies into one block of text for multi-mention extraction.
    """
    # Strip trailing slash before appending .json
    json_url = url.rstrip("/") + _REDDIT_JSON_SUFFIX
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "coffee-app-crawler/1.0"},
            follow_redirects=True,
            timeout=_FETCH_TIMEOUT,
        ) as client:
            resp = await client.get(json_url)
            resp.raise_for_status()
            data = resp.json()

        parts: list[str] = []

        # data[0] = thread listing, data[1] = comments listing
        if isinstance(data, list) and len(data) >= 1:
            thread_children = data[0].get("data", {}).get("children", [])
            for child in thread_children:
                post = child.get("data", {})
                if post.get("selftext"):
                    parts.append(post["selftext"])
                if post.get("title"):
                    parts.append(post["title"])

        if isinstance(data, list) and len(data) >= 2:
            _extract_comment_bodies(data[1].get("data", {}).get("children", []), parts)

        return "\n\n".join(parts)

    except Exception as exc:
        logger.warning("retroactive_matcher: failed to fetch Reddit JSON %s: %s", url, exc)
        return ""


def _extract_comment_bodies(children: list, parts: list[str], depth: int = 0) -> None:
    """Recursively extract comment body text from Reddit JSON comment tree."""
    if depth > 5:
        return
    for child in children:
        data = child.get("data", {})
        body = data.get("body", "")
        if body and body != "[deleted]" and body != "[removed]":
            parts.append(body)
        replies = data.get("replies", {})
        if isinstance(replies, dict):
            reply_children = replies.get("data", {}).get("children", [])
            _extract_comment_bodies(reply_children, parts, depth + 1)


async def _fetch_generic_text(url: str) -> str:
    """Fetch a non-Reddit URL and return plain text content."""
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "coffee-app-crawler/1.0"},
            follow_redirects=True,
            timeout=_FETCH_TIMEOUT,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning("retroactive_matcher: failed to fetch %s: %s", url, exc)
        return ""


async def run_retroactive_match(
    center_lat: float,
    center_lng: float,
    settings,
    region_id: str | None = None,
    since: datetime | None = None,
) -> dict:
    """
    Process all original crawl mentions that haven't been through multi-mention
    extraction yet (place_name_raw='' AND is_multi_processed=FALSE).

    Args:
        center_lat / center_lng: Used as location bias for place_resolver.
        settings: App settings (from config.get_settings()).
        region_id: Unused for filtering (mentions have no region_id); kept for
                   logging context only.
        since: When provided, restricts to mentions created >= this timestamp.
               Used by seed_job to scope to the just-completed crawl.

    Returns:
        dict with keys: processed, places_resolved, urls_failed
    """
    from crawler import db_writer, llm_extractor, place_resolver
    from crawler.multi_mention_extractor import extract_all_mentions
    from services.supabase_client import get_supabase

    logger.info(
        "retroactive_matcher: starting (region=%s, since=%s)",
        region_id,
        since.isoformat() if since else "all",
    )

    # --- Query unprocessed original crawl rows ---
    def _fetch_rows():
        db = get_supabase()
        query = (
            db.table("mentions")
            .select("id, url, source_id")
            .eq("place_name_raw", "")
            .eq("is_multi_processed", False)
        )
        if since is not None:
            query = query.gte("created_at", since.isoformat())
        return query.execute().data

    rows = await asyncio.to_thread(_fetch_rows)
    logger.info("retroactive_matcher: %d rows to process", len(rows))

    processed = 0
    places_resolved = 0
    urls_failed = 0
    resolve_cache: dict = {}

    for row in rows:
        url: str = row["url"]
        mention_id: str = row["id"]
        source_id: str = row["source_id"]

        try:
            # Fetch content
            if _is_reddit_url(url):
                raw_text = await _fetch_reddit_text(url)
            else:
                raw_text = await _fetch_generic_text(url)

            if not raw_text.strip():
                logger.debug("retroactive_matcher: empty content for %s — marking processed", url)
                await db_writer.mark_mention_multi_processed(mention_id)
                processed += 1
                await asyncio.sleep(_INTER_URL_DELAY)
                continue

            # Extract all mentioned places
            mentions = await extract_all_mentions(raw_text, settings.openai_api_key)
            logger.info(
                "retroactive_matcher: %s → %d place(s) extracted",
                url,
                len(mentions),
            )

            # Resolve and write each place
            for mention in mentions:
                if not mention.place_name:
                    continue
                try:
                    resolved = await place_resolver.resolve_place(
                        raw_text=mention.place_name,
                        location_lat=center_lat,
                        location_lng=center_lng,
                        api_key=settings.google_places_api_key,
                        openai_api_key=settings.openai_api_key,
                        similarity_threshold=settings.place_resolver_similarity_threshold,
                        distance_threshold_m=settings.place_resolver_distance_threshold_meters,
                        _cache=resolve_cache,
                    )
                    if not resolved:
                        logger.debug(
                            "retroactive_matcher: could not resolve %r from %s",
                            mention.place_name,
                            url,
                        )
                        continue

                    # Build an ExtractionResult from the MultiMentionResult fields
                    extraction = llm_extractor.ExtractionResult(
                        has_wifi=mention.has_wifi,
                        has_outlets=mention.has_outlets,
                        is_laptop_friendly=mention.is_laptop_friendly,
                        noise_level=mention.noise_level,
                        wifi_confidence=mention.wifi_confidence,
                        outlet_confidence=mention.outlet_confidence,
                        noise_confidence=mention.noise_confidence,
                        laptop_confidence=mention.laptop_confidence,
                        evidence_snippet=mention.evidence_snippet,
                    )

                    inserted = await db_writer.write_multi_mention(
                        resolved=resolved,
                        region_id=region_id,  # None is fine — db_writer skips it
                        source_id=source_id,
                        extraction=extraction,
                        url=url,
                        place_name_raw=mention.place_name.lower(),
                    )
                    if inserted:
                        places_resolved += 1
                        logger.info(
                            "  → wrote %s (place_id=%s)", resolved.name, resolved.place_id
                        )

                except Exception as place_exc:
                    logger.warning(
                        "retroactive_matcher: failed resolving %r from %s: %s",
                        mention.place_name,
                        url,
                        place_exc,
                    )

            # Mark original row as processed regardless of how many places resolved
            await db_writer.mark_mention_multi_processed(mention_id)
            processed += 1

        except Exception as exc:
            logger.warning("retroactive_matcher: failed processing %s: %s", url, exc)
            urls_failed += 1

        await asyncio.sleep(_INTER_URL_DELAY)

    summary = {"processed": processed, "places_resolved": places_resolved, "urls_failed": urls_failed}
    logger.info("retroactive_matcher: done — %s", summary)
    return summary
