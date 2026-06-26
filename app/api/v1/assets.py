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
    MarkStaleRequest,
    MarkStaleResponse,
)
from app.schemas.bulk import BulkAssetCreate, BulkImportResponse
from app.schemas.filters import AssetFilters
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


@router.post(
    "/bulk",
    response_model=BulkImportResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk import assets",
    description="Import multiple assets at once. Uses partial success model — valid assets are created, invalid ones are reported with errors.",
)
async def bulk_import(
    data: BulkAssetCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    POST /api/v1/assets/bulk

    Why is this route defined BEFORE /{asset_id}?
    FastAPI matches routes in order. If /bulk came after /{asset_id},
    FastAPI would try to parse "bulk" as a UUID and return 422.

    Why 200 instead of 201?
    Bulk import is a mixed operation — some items may succeed and others
    may fail. 200 "OK" is more appropriate than 201 "Created" when the
    result is not guaranteed to be all-success.
    """
    return await asset_service.bulk_import(db, data.items)


@router.post(
    "/mark-stale",
    response_model=MarkStaleResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk mark assets as stale",
    description=(
        "Marks all active assets as stale if their last_seen timestamp "
        "is older than the specified threshold in days."
    ),
)
async def mark_stale(
    data: MarkStaleRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    POST /api/v1/assets/mark-stale

    Why is this route defined BEFORE /{asset_id}?
    Same reason as /bulk — FastAPI matches routes in order.
    If /mark-stale came after /{asset_id}, FastAPI would try
    to parse "mark-stale" as a UUID and return 422.

    Example request body:
        {"threshold_days": 30}

    This would mark all active assets with last_seen older than
    30 days ago as stale. The response reports how many were affected.
    """
    return await asset_service.mark_stale(db, data.threshold_days)


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
    description="Returns a paginated list of assets with optional filtering, sorting, and pagination.",
)
async def list_assets(
    filters: AssetFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    GET /api/v1/assets?type=domain&status=active&tag=prod&sort_by=created_at&sort_order=desc&page=1&page_size=20

    All query parameters are optional. When omitted, defaults apply:
    - No filters (returns all assets)
    - sort_by=created_at, sort_order=desc (newest first)
    - page=1, page_size=20

    Using Depends(AssetFilters) tells FastAPI to create an AssetFilters
    instance from the query parameters. Each field in AssetFilters becomes
    a separate query parameter in the Swagger UI.
    """
    return await asset_service.list_assets(db, filters=filters)


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
