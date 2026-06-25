"""
API route handlers for asset operations.

This is the HTTP layer — it knows about:
- HTTP methods (GET, POST, PUT, PATCH, DELETE)
- Status codes (201 Created, 204 No Content, 404 Not Found)
- Query parameters and path parameters
- Pydantic schemas for request/response validation

It does NOT know about:
- SQLAlchemy models or database queries (that's the repository)
- Business rules like deduplication (that's the service)

Each route handler follows the same pattern:
1. Receive the request (FastAPI parses and validates it)
2. Get the database session (via Depends)
3. Call the service layer
4. Return the response
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.asset import (
    AssetCreate,
    AssetListResponse,
    AssetPatch,
    AssetResponse,
    AssetUpdate,
)
from app.services.asset_service import asset_service

# Create a router with a prefix and tag.
# - prefix: all routes in this file start with /api/v1/assets
# - tags: groups these endpoints in the Swagger UI
router = APIRouter(prefix="/api/v1/assets", tags=["Assets"])


@router.post(
    "",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new asset",
    description="Creates a new asset in the system. Requires at minimum a type and value.",
)
async def create_asset(
    data: AssetCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    POST /api/v1/assets

    Why 201 instead of 200?
    HTTP 201 means "a new resource was created." It's semantically correct
    for POST operations that create data, and it tells the client that
    the operation resulted in a new resource (not just a successful action).
    """
    return await asset_service.create_asset(db, data)


@router.get(
    "/{asset_id}",
    response_model=AssetResponse,
    summary="Get an asset by ID",
    description="Retrieves a single asset by its UUID. Returns 404 if not found.",
)
async def get_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    GET /api/v1/assets/{asset_id}

    FastAPI automatically validates that asset_id is a valid UUID.
    If the client sends a malformed UUID, FastAPI returns 422 before
    our code even runs.
    """
    return await asset_service.get_asset(db, asset_id)


@router.get(
    "",
    response_model=AssetListResponse,
    summary="List all assets",
    description="Returns a paginated list of assets. Filtering and sorting added in Milestone 5.",
)
async def list_assets(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    db: AsyncSession = Depends(get_db),
):
    """
    GET /api/v1/assets?page=1&page_size=20

    Query parameters:
    - page: which page to return (1-indexed, not 0-indexed, because
      that's what humans expect)
    - page_size: how many items per page (capped at 100 to prevent
      clients from requesting the entire database)
    """
    return await asset_service.list_assets(db, page=page, page_size=page_size)


@router.put(
    "/{asset_id}",
    response_model=AssetResponse,
    summary="Full update of an asset",
    description="Replaces all fields of an existing asset. PUT = full replacement.",
)
async def update_asset(
    asset_id: UUID,
    data: AssetUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    PUT /api/v1/assets/{asset_id}

    PUT vs PATCH:
    - PUT replaces the ENTIRE resource. If you omit a field, it gets
      the default value (e.g., tags defaults to []).
    - PATCH updates ONLY the fields you send.
    """
    return await asset_service.update_asset(db, asset_id, data)


@router.patch(
    "/{asset_id}",
    response_model=AssetResponse,
    summary="Partial update of an asset",
    description="Updates only the provided fields. PATCH = partial update.",
)
async def patch_asset(
    asset_id: UUID,
    data: AssetPatch,
    db: AsyncSession = Depends(get_db),
):
    """
    PATCH /api/v1/assets/{asset_id}

    Example: sending {"status": "stale"} only changes the status,
    leaving type, value, tags, and everything else untouched.
    """
    return await asset_service.patch_asset(db, asset_id, data)


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an asset",
    description="Permanently removes an asset and its relationships (cascade delete).",
)
async def delete_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    DELETE /api/v1/assets/{asset_id}

    Why 204 No Content?
    The resource has been deleted — there's nothing to return.
    204 means "success, but no response body." This is the standard
    HTTP status code for successful DELETE operations.
    """
    await asset_service.delete_asset(db, asset_id)
