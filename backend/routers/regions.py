"""
Admin-only routes for region inspection and manual seed triggering.
Not called by the frontend. Protected by X-Admin-Key header.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel

from config import Settings, get_settings
from models.region import RegionRow
from services import supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/regions", tags=["regions"])


def _require_admin(x_admin_key: str = Header(default=""), settings: Settings = Depends(get_settings)):
    if not settings.admin_key or x_admin_key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/", response_model=list[RegionRow], dependencies=[Depends(_require_admin)])
async def list_regions() -> list[RegionRow]:
    rows = await supabase_client.list_all_regions()
    return [RegionRow(**r) for r in rows]


@router.post("/{region_id}/seed", dependencies=[Depends(_require_admin)])
async def manual_seed(region_id: str) -> dict:
    from background.seed_job import trigger_seed
    import asyncio

    asyncio.create_task(trigger_seed(region_id))
    return {"status": "seed triggered", "region_id": region_id}


class RetroactiveMatchRequest(BaseModel):
    center_lat: float
    center_lng: float
    region_id: str | None = None


@router.post("/retroactive-match", dependencies=[Depends(_require_admin)])
async def trigger_retroactive_match(
    req: RetroactiveMatchRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Trigger retroactive multi-mention resolution for all unprocessed crawl rows.
    Runs as a FastAPI BackgroundTask (non-blocking). since=None means all rows.
    Protected by X-Admin-Key header.
    """
    from background.retroactive_matcher import run_retroactive_match

    background_tasks.add_task(
        run_retroactive_match,
        req.center_lat,
        req.center_lng,
        settings,
        req.region_id,
        None,  # since=None — process all unprocessed rows
    )
    return {"status": "started", "region_id": req.region_id}
