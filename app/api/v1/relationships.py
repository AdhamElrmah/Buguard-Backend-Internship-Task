"""
API route handlers for relationship operations.

Relationships live on TWO different URL prefixes:
    /api/v1/relationships      → for creating and deleting relationships
    /api/v1/assets/{id}/...    → for listing an asset's relationships

Why two prefixes?
    - Creating/deleting a relationship is about the RELATIONSHIP resource,
      so it lives under /relationships.
    - Listing relationships for an asset is about the ASSET resource,
      so it lives under /assets/{id}/relationships. This is a common
      REST pattern for sub-resources.

We use TWO separate routers and register both in main.py.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_api_key
from app.schemas.relationship import (
    RelationshipCreate,
    RelationshipResponse,
    AssetGraphResponse,
)
from app.services.relationship_service import relationship_service


# --- Router 1: Relationship CRUD ---
# Handles create and delete operations on the relationship resource itself.
relationship_router = APIRouter(
    prefix="/api/v1/relationships",
    tags=["Relationships"],
)


# --- Router 2: Asset Sub-Resource ---
# Handles listing relationships as a sub-resource of an asset.
# We use a separate router because the URL prefix is different
# (/api/v1/assets vs /api/v1/relationships).
asset_relationship_router = APIRouter(
    prefix="/api/v1/assets",
    tags=["Relationships"],
)


@relationship_router.post(
    "",
    response_model=RelationshipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new relationship",
    description=(
        "Creates a directed relationship between two assets. "
        "Both assets must exist. Duplicate relationships are rejected with 409."
    ),
    dependencies=[Depends(verify_api_key)],
)
async def create_relationship(
    data: RelationshipCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    POST /api/v1/relationships

    Request body:
        {
            "source_asset_id": "uuid-of-source",
            "target_asset_id": "uuid-of-target",
            "relationship_type": "belongs_to"
        }

    The service validates:
    1. Source asset exists (404 if not)
    2. Target asset exists (404 if not)
    3. Relationship doesn't already exist (409 if duplicate)
    """
    return await relationship_service.create_relationship(db, data)


@asset_relationship_router.get(
    "/{asset_id}/relationships",
    response_model=list[RelationshipResponse],
    summary="Get all relationships for an asset",
    description=(
        "Returns all relationships where the given asset is either "
        "the source or target. Returns 404 if the asset doesn't exist."
    ),
)
async def get_asset_relationships(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    GET /api/v1/assets/{asset_id}/relationships

    Returns relationships in BOTH directions:
    - Relationships where this asset is the SOURCE (outgoing edges)
    - Relationships where this asset is the TARGET (incoming edges)

    This gives a complete picture of how the asset connects to others.
    """
    return await relationship_service.get_asset_relationships(db, asset_id)


@asset_relationship_router.get(
    "/{asset_id}/graph",
    response_model=AssetGraphResponse,
    summary="Get the graph around an asset",
    description=(
        "Returns the queried asset details together with all its related assets "
        "(both incoming and outgoing relationships)."
    ),
)
async def get_asset_graph(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    GET /api/v1/assets/{asset_id}/graph
    """
    return await relationship_service.get_asset_graph(db, asset_id)


@relationship_router.delete(
    "/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a relationship",
    description="Permanently removes a relationship. Returns 404 if not found.",
    dependencies=[Depends(verify_api_key)],
)
async def delete_relationship(
    relationship_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    DELETE /api/v1/relationships/{relationship_id}

    Why 204 No Content?
    The relationship has been deleted — there's nothing to return.
    Same convention as the asset DELETE endpoint.
    """
    await relationship_service.delete_relationship(db, relationship_id)
