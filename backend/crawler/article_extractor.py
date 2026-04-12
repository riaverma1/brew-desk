"""
LLM-based article extractor: reads a full article and returns every named
coffee shop / cafe as an individual mention with WFH confidence scores.

Replaces both llm_extractor.py (single-place) and multi_mention_extractor.py
(retroactive multi-place). The first pass now handles multi-mention natively.

Model: gpt-4o-mini — cheap, JSON mode, temperature=0.
Input: up to 4000 chars of article text.
Output: list[MentionExtraction] — one per named place. Empty list if none found.

Confidence score semantics:
  wifi_confidence    0.0–1.0  high = good WiFi mentioned
  outlet_confidence  0.0–1.0  high = outlets/power mentioned
  quiet_confidence   0.0–1.0  high = QUIET (good for WFH); low = loud/noisy
  laptop_confidence  0.0–1.0  high = explicitly WFH/laptop friendly
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_openai_client: AsyncOpenAI | None = None


def get_openai_client(api_key: str) -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=api_key, timeout=45.0)
    return _openai_client


SYSTEM_PROMPT = """\
You are a WFH (work-from-home) cafe analyst. Given a piece of text, extract every
named coffee shop or cafe that is mentioned.

For each named place, return:
  - place_name_raw: the name exactly as it appears in the text
  - evidence_snippet: a SHORT verbatim quote (≤ 100 chars) that best supports the
    WFH assessment — must be copied directly from the text, no paraphrasing
  - wifi_confidence: 0.0–1.0. High if good WiFi is mentioned, 0.0 if not mentioned.
  - outlet_confidence: 0.0–1.0. High if outlets/charging is mentioned, 0.0 if not.
  - quiet_confidence: 0.0–1.0. HIGH means QUIET (good for focus). LOW means LOUD.
    Use 0.5 (neutral) if not mentioned.
  - laptop_confidence: 0.0–1.0. High if the place is explicitly described as good
    for working, WFH, remote work, or laptop use. 0.0 if not mentioned.

Scoring signals:
  laptop_confidence HIGH (0.7–1.0): "great for working", "WFH spot", "laptop friendly",
    "remote workers welcome", "stayed for hours", "quiet and productive"
  laptop_confidence LOW (0.0–0.2): "no laptop policy", "time limit", "standing only",
    "crowded", "tables are tiny", "not a place to linger"
  quiet_confidence HIGH (0.7–1.0): "very quiet", "calm", "subdued", "library vibes",
    "can hear yourself think"
  quiet_confidence LOW (0.0–0.3): "blasting music", "loud", "noisy", "hard to focus",
    "packed and chaotic"

Rules:
  - Only include places EXPLICITLY NAMED in the text. Do not infer or hallucinate.
  - evidence_snippet MUST be a verbatim quote — never a summary or paraphrase.
  - Return [] if no named coffee shops are found.
  - Return valid JSON only — an array of objects, no markdown.

Return format (JSON array):
[
  {
    "place_name_raw": "Cafe Grumpy",
    "evidence_snippet": "Cafe Grumpy is my go-to WFH spot — fast wifi and tons of outlets",
    "wifi_confidence": 0.9,
    "outlet_confidence": 0.8,
    "quiet_confidence": 0.6,
    "laptop_confidence": 0.95
  },
  ...
]"""


@dataclass
class MentionExtraction:
    place_name_raw: str
    evidence_snippet: str | None = None
    wifi_confidence: float = 0.0
    outlet_confidence: float = 0.0
    quiet_confidence: float = 0.5
    laptop_confidence: float = 0.0


async def extract_all_mentions(
    raw_text: str,
    openai_api_key: str,
) -> list[MentionExtraction]:
    """
    Extract all named coffee shops from raw_text.
    Returns one MentionExtraction per named place, or [] if none found.
    Never raises — returns [] on failure.
    """
    if not raw_text or not raw_text.strip():
        return []

    client = get_openai_client(openai_api_key)
    truncated = raw_text[:4000]

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
                        'Return JSON with a single key "mentions" containing the array.\n\n'
                        + truncated
                    ),
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)

        # Support both {"mentions": [...]} and bare [...] responses
        items = data.get("mentions", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            logger.warning("article_extractor: unexpected response shape: %r", type(items))
            return []

        results: list[MentionExtraction] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("place_name_raw", "").strip()
            if not name:
                continue
            results.append(
                MentionExtraction(
                    place_name_raw=name,
                    evidence_snippet=item.get("evidence_snippet") or None,
                    wifi_confidence=float(item.get("wifi_confidence", 0.0)),
                    outlet_confidence=float(item.get("outlet_confidence", 0.0)),
                    quiet_confidence=float(item.get("quiet_confidence", 0.5)),
                    laptop_confidence=float(item.get("laptop_confidence", 0.0)),
                )
            )

        logger.info("article_extractor: extracted %d mentions", len(results))
        return results

    except Exception as exc:
        logger.warning("article_extractor: extraction failed: %s", exc)
        return []
