"""
GET /places/{place_id}/mentions — click-to-expand flow.
Returns mentions ordered by laptop_confidence DESC. Limit 20 (Phase 1 safety valve).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from config import Settings, get_settings
from models.mention import MentionCardResponse, MentionsResponse
from services import supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/places", tags=["mentions"])


@router.get("/{place_id}/mentions", response_model=MentionsResponse)
async def get_mentions(
    place_id: str,
    settings: Settings = Depends(get_settings),
) -> MentionsResponse:
    rows = await supabase_client.get_mentions_for_place(place_id)

    mentions = [
        MentionCardResponse(
            id=str(row["id"]),
            url=row["url"],
            evidence_snippet=row.get("evidence_snippet"),
            platform=row["sources"]["platform"],
            handle_or_domain=row["sources"]["handle_or_domain"],
            laptop_confidence=row["laptop_confidence"],
            mentioned_at=str(row["mentioned_at"]) if row.get("mentioned_at") else None,
        )
        for row in rows
    ]

    return MentionsResponse(place_id=place_id, mentions=mentions)
