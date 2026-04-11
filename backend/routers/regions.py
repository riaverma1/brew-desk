"""
Admin-only routes for region inspection and manual seed triggering.
Not called by the frontend. Protected by X-Admin-Key header.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException

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
