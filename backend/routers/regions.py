"""
Admin-only routes for region inspection and manual seed/resolve triggering.
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
    """Manually trigger the full pipeline (crawl → resolve) for a region."""
    import asyncio
    from background.seed_job import trigger_seed
    asyncio.create_task(trigger_seed(region_id))
    return {"status": "seed triggered", "region_id": region_id}


class ResolveRequest(BaseModel):
    center_lat: float
    center_lng: float
    region_id: str


@router.post("/{region_id}/enrich", dependencies=[Depends(_require_admin)])
async def enrich_region_places(
    region_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    force: bool = False,
) -> dict:
    """
    Batch-enrich places in a region via Place Details API. Rate-limited to 5 req/s.
    Runs as a background task — returns immediately.

    force=true re-enriches all places regardless of last_enriched_at (use to
    fix stale/broken photo URLs after a photo pipeline change).
    """
    from background.enrich_job import enrich_unenriched_places

    background_tasks.add_task(enrich_unenriched_places, region_id, settings.google_places_api_key, force=force)
    return {"status": "enrichment started", "region_id": region_id, "force": force}


@router.post("/resolve", dependencies=[Depends(_require_admin)])
async def trigger_resolve(
    req: ResolveRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Manually trigger Step 2 (resolve) for a region.
    Useful if the resolver failed mid-run or if new mentions need resolution.
    Runs as a FastAPI BackgroundTask (non-blocking).
    """
    from background.resolver_job import resolve_for_region

    background_tasks.add_task(
        resolve_for_region,
        req.region_id,
        req.center_lat,
        req.center_lng,
    )
    return {"status": "resolver started", "region_id": req.region_id}
