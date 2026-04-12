# backend/enrichment/web_searches.py
"""
Tavily + LangChain agent for WFH enrichment of a place dict.

- Uses TavilySearch from `langchain_tavily`
- Uses `create_agent` from `langchain.agents` (per Tavily docs)
- Input: `place` dict (name, formatted_address, neighborhood/region, etc.)
- Agent:
    - Uses TavilySearch to look up WFH-relevant info
    - Decides its own queries
    - Returns STRICT JSON with WFH attributes + evidence
- Output: WebEnrichmentResult (Pydantic) with attributes + evidence + cache_key.

Env:
  export OPENAI_API_KEY="..."
  export TAVILY_API_KEY="..."

"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch

logger = logging.getLogger(__name__)


# =============================================================================
# Data models
# =============================================================================

class Evidence(BaseModel):
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    quote: Optional[str] = None  # short excerpt supporting a key claim


class PlaceAttributes(BaseModel): 
    wifi_quality: str = Field(default="unknown", description="good|mixed|bad|unknown")
    outlet_availability: str = Field(default="many|few|none|unknown")
    noise_level: str = Field(default="quiet|mixed|loud|unknown")
    laptop_friendly: str = Field(default="yes|mixed|no|unknown")
    seating_comfort: str = Field(default="good|mixed|bad|unknown")

    common_complaints: List[str] = Field(default_factory=list)
    notable_positives: List[str] = Field(default_factory=list)

    wfh_overall: str = Field(
        default="unknown",
        description="yes|mixed|no|unknown",
    )

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str = Field(default="", description="<= 20 words summary of WFH suitability")


class WebEnrichmentResult(BaseModel):
    # identifiers from your system
    place_id: Optional[str] = None
    place_name: str
    address: Optional[str] = None
    neighborhood: Optional[str] = None
    website: Optional[str] = None

    fetched_at_utc: int
    cache_key: str

    # output
    attributes: PlaceAttributes
    evidence: List[Evidence] = Field(default_factory=list)

    # raw / debug
    raw_agent_output: Optional[str] = None


# =============================================================================
# Helpers
# =============================================================================

def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def build_cache_key(
    *,
    place_id: Optional[str],
    name: str,
    address: Optional[str],
    neighborhood: Optional[str],
) -> str:
    """
    Prefer place_id if you have it; else hash normalized name+address+neighborhood.
    """
    if place_id:
        return f"web_enrich_agent:v1:pid:{place_id}"

    base = "|".join(
        _norm_ws(x).lower()
        for x in [name, address or "", neighborhood or ""]
        if x is not None
    )
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return f"web_enrich_agent:v1:hash:{h}"


def _strip_json_code_fence(text: str) -> str:
    """
    Handle ```json ...``` or ``` ... ``` fences if the model uses them.
    """
    t = text.strip()
    if not t.startswith("```"):
        return t

    lines = t.splitlines()
    # drop first fence line
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    # drop last fence line if present
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_text_from_agent_output(resp: Any) -> str:
    """
    Extract the final text from the `agent.invoke` response.
    The Tavily docs example just prints `step["messages"][-1].pretty_print()`,
    but `create_agent` in Python returns a dict-like structure we can inspect.
    """
    if isinstance(resp, str):
        return resp

    if isinstance(resp, dict):
        # Some LC versions return `{"messages": [...]}`
        msgs = resp.get("messages")
        if isinstance(msgs, list) and msgs:
            last = msgs[-1]
            content = getattr(last, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(last, dict) and isinstance(last.get("content"), str):
                return last["content"]

        # Some versions return `{"output": "..."}` for convenience
        if isinstance(resp.get("output"), str):
            return resp["output"]

    # Fallback
    return str(resp)


# =============================================================================
# Agent construction (aligned with Tavily docs)
# =============================================================================

WFH_SYSTEM_PROMPT = """
You are a specialized research assistant that evaluates whether a specific coffee shop
or location is a good spot to work from home (WFH).

You have access to a TavilySearch tool and should:
- Use web search to find reviews, blog posts, Reddit threads, and listicles about working from that location.
- Focus on attributes related to working from a laptop for extended periods.

Your task for EACH request:
1) Decide the best Tavily queries to run, based on the place information provided.
2) Call the TavilySearch tool as needed to gather evidence.
3) Parse the information and return STRICT JSON with this exact schema and keys:

{
  "attributes": {
    "wifi_quality": "good|mixed|bad|unknown",
    "outlet_availability": "many|few|none|unknown",
    "noise_level": "quiet|mixed|loud|unknown",
    "laptop_friendly": "yes|mixed|no|unknown",
    "seating_comfort": "good|mixed|bad|unknown",
    "common_complaints": ["string"],
    "notable_positives": ["string"],
    "wfh_overall": "yes|mixed|no|unknown",
    "confidence": 0.0,
    "summary": "short <= 20 word summary"
  },
  "evidence": [
    {
      "url": "string",
      "title": "string or null",
      "snippet": "string or null",
      "quote": "short supporting excerpt or null"
    }
  ]
}

Rules:
- If you are uncertain about a field, set it to "unknown" and lower confidence.
- Use at most 8 evidence items.
- Each evidence item should directly support at least one attribute.
- Return ONLY the JSON object above, with no markdown, no additional text, and no comments.
"""

def build_wfh_agent():
    """
    Build a Tavily-backed agent exactly like the Tavily docs:

        from langchain_tavily import TavilySearch
        from langchain.agents import create_agent

        tavily_search_tool = TavilySearch(max_results=5, topic="general")
        agent = create_agent(model, [tavily_search_tool])

    plus our system prompt.
    """
    llm = ChatOpenAI(
        model="gpt-5-mini",
        temperature=0,
        # IMPORTANT: do NOT use JSON mode (response_format) with tools.
        # That is what caused the "tavily_search is not strict" error.
    )

    tavily_search_tool = TavilySearch(
        max_results=8,
        topic="general",
        include_answer=False,
        include_raw_content=False,  # keep token usage small
        search_depth="basic",
    )

    # Tavily example uses: agent = create_agent(model, [tavily_search_tool])
    agent = create_agent(
        llm,
        [tavily_search_tool],
    )

    return agent


# =============================================================================
# Public entrypoint
# =============================================================================

def enrich_place_with_agent(
    place: Dict[str, Any],
    *,
    place_id: Optional[str] = None,
) -> WebEnrichmentResult:
    """
    Main function: given a place dict, run the Tavily-backed LangChain agent
    and return structured WFH attributes + evidence.

    Expected place keys (flexible):
      - name
      - formatted_address or address
      - neighborhood / vicinity / region
      - website
      - types, rating, user_ratings_total, etc.
    """

    name = place.get("name") or "Unknown"
    address = (
        place.get("formatted_address")
        or place.get("address")
        or None
    )
    neighborhood = (
        place.get("neighborhood")
        or place.get("vicinity")
        or place.get("region")
        or None
    )
    website = place.get("website") or None

    fetched_at = int(time.time())
    cache_key = build_cache_key(
        place_id=place_id,
        name=name,
        address=address,
        neighborhood=neighborhood,
    )

    agent = build_wfh_agent()

    place_json = json.dumps(place, ensure_ascii=False, indent=2)
    user_content = (
        f"SYSTEM INSTRUCTIONS (for this request only):\n"
        f"{WFH_SYSTEM_PROMPT}\n\n"
        f"USER QUESTION:\n"
        f"Is the location '{name}' in '{neighborhood or ''}' a good spot for work from home?\n"
        f"Find all relevant information regarding this location and its attributes related to work from home.\n\n"
        f"Here is the full place dictionary from my app:\n{place_json}\n\n"
        f"Remember: use the TavilySearch tool to retrieve evidence and then return ONLY the JSON schema described above."
    )

    logger.info("Running WFH web agent for place=%s", name)

    try:
        # Tavily example:
        #   agent.stream({"messages": user_input}, stream_mode="values")
        # Here we just do a single invoke and parse the final message.
        response = agent.invoke({"messages": user_content})
    except Exception as e:
        logger.error("Agent invocation failed for place=%s: %s", name, e)
        attrs = PlaceAttributes(
            summary=f"Agent invocation failed; no WFH signal. Reason: {e}",
            confidence=0.0,
        )
        return WebEnrichmentResult(
            place_id=place_id,
            place_name=name,
            address=address,
            neighborhood=neighborhood,
            website=website,
            fetched_at_utc=fetched_at,
            cache_key=cache_key,
            attributes=attrs,
            evidence=[],
            raw_agent_output=None,
        )

    raw_text = _extract_text_from_agent_output(response)
    logger.debug("Raw agent output (truncated): %s", raw_text[:2000])

    # Parse JSON to Pydantic (with simple fence-stripping)
    try:
        cleaned = _strip_json_code_fence(raw_text)
        parsed = json.loads(cleaned)
        attrs = PlaceAttributes.model_validate(parsed["attributes"])
        evidence = [Evidence.model_validate(e) for e in parsed.get("evidence", [])]
    except Exception as e:
        logger.error("Failed to parse agent JSON output for place=%s: %s", name, e)
        attrs = PlaceAttributes(
            summary="Agent failed to return valid JSON; treating everything as unknown.",
            confidence=0.0,
        )
        evidence = []

    return WebEnrichmentResult(
        place_id=place_id,
        place_name=name,
        address=address,
        neighborhood=neighborhood,
        website=website,
        fetched_at_utc=fetched_at,
        cache_key=cache_key,
        attributes=attrs,
        evidence=evidence,
        raw_agent_output=raw_text,
    )


# =============================================================================
# CLI test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_place = {
        "name": os.getenv("TEST_PLACE_NAME", "Birch Coffee"),
        "formatted_address": os.getenv("TEST_ADDRESS", "21 E 27th St, New York, NY"),
        "neighborhood": os.getenv("TEST_NEIGHBORHOOD", "Flatiron"),
        "website": os.getenv("TEST_WEBSITE", ""),
        "types": ["cafe", "coffee_shop"],
        "region": "Manhattan",
    }

    res = enrich_place_with_agent(
        place=test_place,
        place_id=os.getenv("TEST_PLACE_ID"),
    )

    print(res.model_dump_json(indent=2))
