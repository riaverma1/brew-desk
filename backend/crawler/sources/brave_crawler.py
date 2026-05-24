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

from crawler.sources.tavily_crawler import RawMention, _clean_title, queries_for_slug

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


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
    query_list = queries or queries_for_slug(city_slug)
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
                source_title = _clean_title(result.get("title", ""))
                mentions.append(RawMention(
                    url=url, snippet=snippet, query=query,
                    source="brave", source_title=source_title,
                ))

            await asyncio.sleep(0.3)

    logger.info("Brave: collected %d unique mentions for %s", len(mentions), city_slug)
    return mentions
