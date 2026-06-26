from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1.assets import router as assets_router
from app.api.v1.relationships import (
    asset_relationship_router,
    relationship_router,
)
from app.config import settings
from app.core.database import async_session_factory
from app.core.error_handlers import register_error_handlers

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Asset Management System for the DarkAtlas Attack Surface Monitoring platform.",
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Register Global Error Handlers ---
# Converts all exceptions (custom, validation, unhandled) into a
# consistent JSON response format. Must be called before routes run.
register_error_handlers(app)

# --- Register Routers ---
# Each router handles a resource (assets, relationships, etc.)
# The router's prefix (/api/v1/assets) is defined in the router file itself.
app.include_router(assets_router)
app.include_router(relationship_router)
app.include_router(asset_relationship_router)


@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint.

    Verifies both the API and database are operational.
    Executes a lightweight SELECT 1 query to confirm database connectivity.
    Returns "degraded" status if the database is unreachable.
    """
    db_status = "healthy"
    db_error = None

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = "unhealthy"
        db_error = str(e)

    overall = "healthy" if db_status == "healthy" else "degraded"

    response = {
        "status": overall,
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status,
    }

    if db_error:
        response["database_error"] = db_error

    return response
