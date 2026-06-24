from fastapi import FastAPI

from app.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Asset Management System for the DarkAtlas Attack Surface Monitoring platform.",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint.

    Returns the application status. Used by Docker, load balancers,
    and monitoring systems to verify the service is running.
    """
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
