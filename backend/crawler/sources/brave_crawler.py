"""
Brave Search API crawler — cheaper bulk URL discovery.
Complements Tavily for neighborhood-level queries where breadth matters.
~$3/1000 queries. 0.3s delay between requests.

Brave requires:
  - Accept: application/json
  - X-Subscription-Token header
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from crawler.sources.tavily_crawler import RawMention

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

MANHATTAN_QUERIES = [
    "best coffee shop work remotely Manhattan neighborhood",
    "cafe laptop friendly Harlem wifi",
    "work from cafe Chelsea Manhattan outlets",
    "best WFH cafe East Village NYC",
    "coffee shop good wifi Williamsburg Brooklyn",
    "quiet cafe work laptop Flatiron NYC",
    "coffee shop no time limit NYC wifi",
    "cafe with power outlets near me Manhattan",
]

QUERIES_BY_SLUG: dict[str, list[str]] = {
    "nyc-manhattan": MANHATTAN_QUERIES,
}


async def fetch_brave_mentions(
    city_slug: str,
    api_key: str,
    queries: list[str] | None = None,
    seen_urls: set[str] | None = None,
) -> list[RawMention]:
    """
    Run Brave Search queries and collect unique URLs + snippets.
    Deduplicates against seen_urls (URLs already collected by Tavily).
    """
    query_list = queries or QUERIES_BY_SLUG.get(city_slug, MANHATTAN_QUERIES)
    seen = seen_urls or set()
    mentions: list[RawMention] = []

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }

    async with httpx.AsyncClient() as client:
        for query in query_list:
            try:
                resp = await client.get(
                    BRAVE_SEARCH_URL,
                    headers=headers,
                    params={"q": query, "count": 10},
                    timeout=10,
                )
                resp.raise_for_status()
                results = resp.json().get("web", {}).get("results", [])
            except Exception as exc:
                logger.warning("Brave query failed: %r — %s", query, exc)
                results = []

            for result in results:
                url = result.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                snippet = result.get("description", "")
                mentions.append(RawMention(url=url, snippet=snippet, query=query, source="brave"))

            await asyncio.sleep(0.3)

    logger.info("Brave: collected %d unique mentions for %s", len(mentions), city_slug)
    return mentions
