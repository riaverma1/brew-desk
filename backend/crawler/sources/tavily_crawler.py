"""
Primary web crawler via Tavily.

Uses search_depth='basic' — returns URLs + short snippets cheaply.
Pages are scraped directly with httpx for full content, avoiding
Tavily's per-result content cost.

~15 queries × $0.01 ≈ $0.15 per region crawl.
0.5s delay between queries to respect rate limits.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser

import httpx

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

MANHATTAN_QUERIES = [
    # City-level
    "best coffee shops work from laptop NYC 2024",
    "WFH friendly cafe New York wifi outlets",
    # Borough/neighborhood-level
    "best cafes to work from Manhattan wifi",
    "work from coffee shop Midtown outlets quiet",
    "cafe wifi outlets Lower East Side Manhattan",
    "coffee shop work SoHo Manhattan",
    "WFH cafe Upper West Side laptop friendly",
    # Attribute-focused
    "NYC coffee shop strong wifi no time limit",
    "quiet cafe Manhattan good for working",
    "NYC cafe lots of outlets work from home",
    # Site-targeted (surfaces Reddit + Yelp without direct API access)
    "site:reddit.com coffee shop work laptop nyc manhattan",
    "site:yelp.com best coffee shops work nyc manhattan",
    "site:nymag.com best cafes work from home NYC",
    "site:timeout.com best NYC cafes to work from",
]

QUERIES_BY_SLUG: dict[str, list[str]] = {
    "nyc-manhattan": MANHATTAN_QUERIES,
}


@dataclass
class RawMention:
    url: str
    snippet: str
    query: str
    source: str = "tavily"
    raw_content: str = ""
    source_title: str | None = None


class _TitleParser(HTMLParser):
    """Minimal HTML parser — extracts og:title meta or first <title> tag."""
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "meta":
            d = dict(attrs)
            if d.get("property") == "og:title" and self.title is None:
                val = (d.get("content") or "").strip()
                if val:
                    self.title = val
        if tag == "title" and self.title is None:
            self._in_title = True

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title is None:
            val = data.strip()
            if val:
                self.title = val
                self._in_title = False

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False


_BOILERPLATE_SEPS = (" | ", " - ", " : ", " – ", " — ")


def _clean_title(raw: str | None) -> str | None:
    """Strip site-name suffixes and reject boilerplate-only results."""
    if not raw:
        return None
    t = raw.strip()
    for sep in _BOILERPLATE_SEPS:
        if sep in t:
            t = t.split(sep)[0].strip()
            break
    return t if len(t) >= 5 else None


def _extract_title_from_html(html: str) -> str | None:
    """Parse og:title or <title> from raw HTML (first 5 KB is enough for <head>)."""
    parser = _TitleParser()
    try:
        parser.feed(html[:5000])
    except Exception:
        return None
    return _clean_title(parser.title)


async def _scrape_url(url: str, client: httpx.AsyncClient) -> tuple[str, str | None]:
    """Scrape a URL; return (truncated_content, page_title)."""
    try:
        resp = await client.get(url, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        title = _extract_title_from_html(html)
        return html[:3000], title
    except Exception as exc:
        logger.debug("Failed to scrape %s: %s", url, exc)
        return "", None


async def fetch_tavily_mentions(
    city_slug: str,
    api_key: str,
    queries: list[str] | None = None,
    seen_urls: set[str] | None = None,
) -> list[RawMention]:
    """
    Run multi-query Tavily search and scrape unique URLs for full content.
    Deduplicates by URL. Passes seen_urls set to avoid re-scraping Brave results.
    """
    query_list = queries or QUERIES_BY_SLUG.get(city_slug, MANHATTAN_QUERIES)
    seen = seen_urls or set()
    mentions: list[RawMention] = []

    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        for i, query in enumerate(query_list, 1):
            logger.info("  Tavily [%d/%d]: %r", i, len(query_list), query)
            try:
                resp = await client.post(
                    TAVILY_SEARCH_URL,
                    headers=headers,
                    json={
                        "api_key": api_key,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": 5,
                        "include_answer": False,
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
            except Exception as exc:
                logger.warning("  Tavily query failed: %r — %s", query, exc)
                results = []

            new_this_query = 0
            for result in results:
                url = result.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                snippet = result.get("content", "")
                # Tavily API returns a title field; use it, fall back to HTML parse
                api_title = _clean_title(result.get("title", ""))
                raw_content, html_title = await _scrape_url(url, client)
                source_title = api_title or html_title
                mentions.append(RawMention(
                    url=url, snippet=snippet, query=query,
                    raw_content=raw_content, source_title=source_title,
                ))
                new_this_query += 1

            logger.info("  Tavily [%d/%d]: %d new URLs (running total: %d)", i, len(query_list), new_this_query, len(mentions))
            await asyncio.sleep(0.5)

    logger.info("Tavily: collected %d unique mentions for %s", len(mentions), city_slug)
    return mentions
