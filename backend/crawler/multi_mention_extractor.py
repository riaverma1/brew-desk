"""
Extracts ALL coffee shop / cafe mentions from a single piece of text.

Unlike llm_extractor.py (one place, 800 chars truncation, single JSON object),
this module:
  - accepts up to 4000 chars of text (Reddit threads, blog list posts, etc.)
  - returns a JSON *array* — one item per distinct named place
  - is called only by the retroactive matcher, never by the hot crawl path

Cost: one gpt-4o-mini call per URL processed by the retroactive job.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_MAX_CHARS = 4000

_openai_client: AsyncOpenAI | None = None


def get_openai_client(api_key: str) -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=api_key, timeout=30.0)
    return _openai_client


SYSTEM_PROMPT = """You are extracting coffee shop and cafe mentions from text that may list or discuss multiple places.

Return a JSON array of ALL distinct coffee shops or cafes explicitly named in the text.
For each named place include:
  - place_name: the cafe/coffee shop name as written in the text (string, required)
  - evidence_snippet: a verbatim direct quote from the text that mentions this place (string or null)
  - has_wifi: true | false | null (only if explicitly mentioned)
  - has_outlets: true | false | null (only if explicitly mentioned)
  - is_laptop_friendly: true | false | null (only if explicitly mentioned)
  - noise_level: "quiet" | "moderate" | "loud" | null (only if explicitly mentioned)
  - wifi_confidence: 0.0–1.0
  - outlet_confidence: 0.0–1.0
  - noise_confidence: 0.0–1.0
  - laptop_confidence: 0.0–1.0

Rules:
- Only include places that are explicitly named — do not infer or hallucinate names.
- evidence_snippet MUST be a verbatim quote from the text, never paraphrased.
- Set confidence scores to 0.0 for attributes not mentioned.
- Return [] (empty array) if no named coffee shops or cafes are found.
- Return valid JSON only — no markdown, no prose."""


class MultiMentionResult(BaseModel):
    place_name: str
    evidence_snippet: str | None = None
    has_wifi: bool | None = None
    has_outlets: bool | None = None
    is_laptop_friendly: bool | None = None
    noise_level: Literal["quiet", "moderate", "loud"] | None = None
    wifi_confidence: float = 0.0
    outlet_confidence: float = 0.0
    noise_confidence: float = 0.0
    laptop_confidence: float = 0.0


async def extract_all_mentions(
    raw_text: str,
    openai_api_key: str,
) -> list[MultiMentionResult]:
    """
    Extract all named coffee shop mentions from raw_text.
    Truncates to 4000 chars. Returns [] on any failure — never raises.
    """
    if not raw_text or not raw_text.strip():
        return []

    client = get_openai_client(openai_api_key)
    truncated = raw_text[:_MAX_CHARS]

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Extract all named coffee shops from this text. "
                        'Return JSON as: {"mentions": [...]}\n\n'
                        f"{truncated}"
                    ),
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)

        # Accept both {"mentions": [...]} and a bare array
        items = data.get("mentions", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            logger.warning("multi_mention_extractor: unexpected response shape")
            return []

        results = []
        for item in items:
            if not isinstance(item, dict) or not item.get("place_name"):
                continue
            try:
                results.append(
                    MultiMentionResult(
                        **{k: v for k, v in item.items() if k in MultiMentionResult.model_fields}
                    )
                )
            except Exception as parse_exc:
                logger.debug("multi_mention_extractor: skipping malformed item: %s", parse_exc)

        return results

    except Exception as exc:
        logger.warning("multi_mention_extractor: extraction failed: %s", exc)
        return []
