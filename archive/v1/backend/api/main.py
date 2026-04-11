"""
FastAPI main application.
"""
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import places

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Coffee App API",
    description="API for coffee/work-friendly places with WFH attributes",
    version="1.0.0",
)

# CORS configuration - supports both production and local development
# Default localhost origins for local development
default_origins = [
    "http://localhost:3000",  # Next.js dev server
    "http://localhost:3001",
]

# Get additional origins from environment variable (for production)
# Format: comma-separated list, e.g., "https://your-app.vercel.app,https://another-domain.com"
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
if allowed_origins_env:
    # Split by comma and strip whitespace
    additional_origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
    # Combine with default localhost origins
    allowed_origins = default_origins + additional_origins
else:
    # No production origins set, use only localhost (for local development)
    allowed_origins = default_origins

logger.info(f"CORS allowed origins: {allowed_origins}")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(places.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Coffee App API", "version": "1.0.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

