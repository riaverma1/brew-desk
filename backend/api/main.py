"""
FastAPI main application.
"""
import logging
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://localhost:3001",
    ],
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

