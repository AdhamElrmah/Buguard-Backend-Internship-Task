"""
Business logic layer for relationships.

Sits between the router (HTTP) and the repository (database).
Handles:
- Validating that both assets exist before creating a relationship
- Detecting and rejecting duplicate relationships (409 Conflict)
- Converting between Pydantic schemas and SQLAlchemy models
"""

from uuid import UUID

from app.core.exceptions import ConflictException, NotFoundException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.relationship import Relationship
from app.repositories.asset_repository import asset_repository
from app.repositories.relationship_repository import relationship_repository
from app.schemas.relationship import (
    RelationshipCreate,
    RelationshipResponse,
)


class RelationshipService:
    """
    Business logic for relationship operations.

    Uses both the asset and relationship repositories:
    - asset_repository: to validate that referenced assets exist
    - relationship_repository: for CRUD on relationships
    """

    def __init__(self):
        self.repo = relationship_repository
        self.asset_repo = asset_repository

    async def create_relationship(
        self, session: AsyncSession, data: RelationshipCreate
    ) -> RelationshipResponse:
        """
        Create a new relationship between two assets.

        Validation steps (in order):
        1. Source asset must exist → 404 if not found
        2. Target asset must exist → 404 if not found
        3. Relationship must not already exist → 409 Conflict if duplicate

        Why check assets exist before inserting?
        We could rely on the database FK constraint to reject invalid
        asset IDs, but that gives a cryptic IntegrityError. Checking
        explicitly lets us return a clear, user-friendly error message
        that says exactly which asset ID was not found.
        """
        # Step 1: Validate source asset exists
        source = await self.asset_repo.get_by_id(session, data.source_asset_id)
        if not source:
            raise NotFoundException(
                f"Source asset with id '{data.source_asset_id}' not found. "
                f"Both assets must exist before creating a relationship."
            )

        # Step 2: Validate target asset exists
        target = await self.asset_repo.get_by_id(session, data.target_asset_id)
        if not target:
            raise NotFoundException(
                f"Target asset with id '{data.target_asset_id}' not found. "
                f"Both assets must exist before creating a relationship."
            )

        # Step 3: Check for duplicate relationship
        # The UNIQUE constraint would catch this at the DB level, but
        # checking here gives a proper 409 response with a clear message.
        existing = await self.repo.get_by_source_target_type(
            session,
            data.source_asset_id,
            data.target_asset_id,
            data.relationship_type.value,
        )
        if existing:
            raise ConflictException(
                f"A '{data.relationship_type.value}' relationship already exists "
                f"between source '{data.source_asset_id}' and "
                f"target '{data.target_asset_id}'."
            )

        # Step 4: Create the relationship
        relationship = Relationship(
            source_asset_id=data.source_asset_id,
            target_asset_id=data.target_asset_id,
            relationship_type=data.relationship_type.value,
        )

        relationship = await self.repo.create(session, relationship)
        await session.commit()
        return RelationshipResponse.model_validate(relationship)

    async def get_asset_relationships(
        self, session: AsyncSession, asset_id: UUID
    ) -> list[RelationshipResponse]:
        """
        Get all relationships for a given asset (both directions).

        Returns relationships where the asset is the source OR target.
        The caller (router) also validates the asset exists first,
        so we get a clear 404 instead of an empty list for bad IDs.
        """
        # Validate the asset exists first
        asset = await self.asset_repo.get_by_id(session, asset_id)
        if not asset:
            raise NotFoundException(
                f"Asset with id '{asset_id}' not found"
            )

        relationships = await self.repo.get_by_asset_id(session, asset_id)
        return [
            RelationshipResponse.model_validate(r) for r in relationships
        ]

    async def delete_relationship(
        self, session: AsyncSession, relationship_id: UUID
    ) -> None:
        """
        Delete a relationship by its ID.

        Raises 404 if the relationship doesn't exist.
        """
        relationship = await self.repo.get_by_id(session, relationship_id)
        if not relationship:
            raise NotFoundException(
                f"Relationship with id '{relationship_id}' not found"
            )

        await self.repo.delete(session, relationship)
        await session.commit()


# Singleton instance — import this in the router
relationship_service = RelationshipService()
