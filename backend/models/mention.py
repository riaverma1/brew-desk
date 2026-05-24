from __future__ import annotations
from typing import Literal
from pydantic import BaseModel

Platform = Literal["reddit", "instagram", "blog", "tiktok", "google_review"]


class MentionCardResponse(BaseModel):
    id: str
    url: str
    evidence_snippet: str | None = None
    platform: Platform
    handle_or_domain: str
    laptop_confidence: float
    mentioned_at: str | None = None
    source_title: str | None = None


class MentionsResponse(BaseModel):
    place_id: str
    mentions: list[MentionCardResponse]
