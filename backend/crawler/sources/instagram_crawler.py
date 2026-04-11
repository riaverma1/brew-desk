"""
Instagram crawler — fetches captions from hardcoded curated public WFH accounts.
Scrapes public profile JSON via httpx (no Selenium). Fragile but supplementary.
On failure, logs and continues — must not block the seed job.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from crawler.sources.tavily_crawler import RawMention

logger = logging.getLogger(__name__)

CURATED_ACCOUNTS = ["workfromcafe", "nycofficelounge", "wfhnyc"]


async def fetch_instagram_mentions(
    accounts: list[str] = CURATED_ACCOUNTS,
) -> list[RawMention]:
    """
    Attempt to fetch recent captions from curated Instagram accounts.
    Each account that should exist as is_curated=True in the sources table.
    Returns an empty list on total failure — never raises.
    """
    mentions: list[RawMention] = []

    async with httpx.AsyncClient() as client:
        for account in accounts:
            try:
                url = f"https://www.instagram.com/{account}/?__a=1&__d=dis"
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10,
                    follow_redirects=True,
                )
                resp.raise_for_status()
                data = resp.json()
                edges = (
                    data.get("graphql", {})
                    .get("user", {})
                    .get("edge_owner_to_timeline_media", {})
                    .get("edges", [])
                )
                for edge in edges[:10]:
                    node = edge.get("node", {})
                    caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
                    caption = caption_edges[0]["node"]["text"] if caption_edges else ""
                    shortcode = node.get("shortcode", "")
                    if not caption or not shortcode:
                        continue
                    ig_url = f"https://www.instagram.com/p/{shortcode}/"
                    mentions.append(
                        RawMention(
                            url=ig_url,
                            snippet=caption[:500],
                            query=f"instagram:{account}",
                            source="instagram",
                            raw_content=caption,
                        )
                    )
            except Exception as exc:
                logger.warning("Instagram scrape failed for @%s: %s", account, exc)
                continue

    logger.info("Instagram: collected %d mentions from %d accounts", len(mentions), len(accounts))
    return mentions
