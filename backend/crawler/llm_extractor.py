"""
Uses GPT to extract structured WFH attributes + confidence scores from raw text.
Uses gpt-4o-mini (not gpt-4o) — ~$0.04/region crawl vs ~$0.40.
temperature=0. Truncate raw_text to 800 chars.
evidence_snippet must be a direct quote — never hallucinated (shown in UI).
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel

_openai_client: AsyncOpenAI | None = None


def get_openai_client(api_key: str) -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=api_key, timeout=30.0)
    return _openai_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a strict WFH attribute extractor for coffee shops.

Given text about a coffee shop, extract WFH-relevant attributes.
Return null for any attribute not mentioned in the text.
Set confidence to 0.0 for unmentioned attributes.
evidence_snippet MUST be a verbatim direct quote from the text — do NOT paraphrase.

Return valid JSON matching this schema:
{
  "has_wifi": true | false | null,
  "has_outlets": true | false | null,
  "is_laptop_friendly": true | false | null,
  "noise_level": "quiet" | "moderate" | "loud" | null,
  "seating_comfort": "<brief description>" | null,
  "wifi_confidence": 0.0-1.0,
  "outlet_confidence": 0.0-1.0,
  "noise_confidence": 0.0-1.0,
  "laptop_confidence": 0.0-1.0,
  "evidence_snippet": "<direct verbatim quote from text>" | null
}"""


class ExtractionResult(BaseModel):
    has_wifi: bool | None = None
    has_outlets: bool | None = None
    is_laptop_friendly: bool | None = None
    noise_level: Literal["quiet", "moderate", "loud"] | None = None
    seating_comfort: str | None = None
    wifi_confidence: float = 0.0
    outlet_confidence: float = 0.0
    noise_confidence: float = 0.0
    laptop_confidence: float = 0.0
    evidence_snippet: str | None = None


_EMPTY_RESULT = ExtractionResult()


async def extract_wfh_attributes(
    raw_text: str,
    place_name: str,
    openai_api_key: str,
) -> ExtractionResult:
    """
    Extract WFH attributes from raw_text mentioning place_name.
    Returns empty ExtractionResult on failure rather than raising.
    """
    client = get_openai_client(openai_api_key)
    truncated = raw_text[:800]

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Place: {place_name}\n\nText:\n{truncated}",
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        return ExtractionResult(**{k: v for k, v in data.items() if k in ExtractionResult.model_fields})
    except Exception as exc:
        logger.warning("LLM extraction failed for %r: %s", place_name, exc)
        return _EMPTY_RESULT
