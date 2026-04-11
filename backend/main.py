"""
FastAPI entry point for V2.
Run with: uvicorn main:app (from backend/ directory)

Key constraints:
- CORS allow_origins: exact Vercel frontend URL, never ["*"] in production
- GET /health: required for Render health check
- APScheduler started via lifespan context manager
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import mentions, places, regions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("V2 backend starting. Frontend URL: %s", settings.frontend_url)
    # APScheduler for weekly re-crawl would be started here (Phase 1 optional)
    # from backend.background.scheduler import start_scheduler
    # start_scheduler()
    yield
    logger.info("V2 backend shutting down.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="WFH Coffee Shop Finder API",
        description="V2 — read-only map view into a pre-built enriched database",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(places.router)
    app.include_router(mentions.router)
    app.include_router(regions.router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/")
    async def root():
        return {"message": "WFH Coffee Shop Finder API", "version": "2.0.0"}

    return app


app = create_app()
