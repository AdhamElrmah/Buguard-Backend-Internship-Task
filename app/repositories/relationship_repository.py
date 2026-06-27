"""
Data access layer for relationships.

Handles all database queries for the relationships table.
Same design as AssetRepository — knows about SQLAlchemy, knows nothing
about HTTP or business rules.
"""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.relationship import Relationship


class RelationshipRepository:
    """Handles all database operations for the Relationship model."""

    async def create(
        self, session: AsyncSession, relationship: Relationship
    ) -> Relationship:
        """
        Insert a new relationship into the database.

        flush() sends the INSERT to the DB so we can detect constraint
        violations (like duplicate relationships) immediately.
        refresh() reloads the object with DB-generated defaults (created_at).
        """
        session.add(relationship)
        await session.flush()
        await session.refresh(relationship)
        return relationship

    async def get_by_id(
        self, session: AsyncSession, relationship_id: UUID
    ) -> Relationship | None:
        """
        Fetch a single relationship by its primary key.

        Returns None if not found — the service layer decides
        whether that's a 404 error.
        """
        return await session.get(Relationship, relationship_id)

    async def get_by_asset_id(
        self, session: AsyncSession, asset_id: UUID
    ) -> list[Relationship]:
        """
        Fetch all relationships where the given asset is either source or target.

        Uses OR to match both directions:
            WHERE source_asset_id = :id OR target_asset_id = :id

        This returns a complete picture of an asset's connections,
        regardless of which "side" of the relationship it's on.

        Example: if asset A has:
            - A → B (belongs_to)
            - C → A (depends_on)
        Both relationships are returned when querying for asset A.
        """
        query = select(Relationship).where(
            or_(
                Relationship.source_asset_id == asset_id,
                Relationship.target_asset_id == asset_id,
            )
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_by_source_target_type(
        self,
        session: AsyncSession,
        source_asset_id: UUID,
        target_asset_id: UUID,
        relationship_type: str,
    ) -> Relationship | None:
        """
        Look up a relationship by its uniqueness key (source, target, type).

        Used by the service layer to check for duplicates before creating.
        This mirrors how get_by_type_and_value works for asset deduplication.
        """
        query = select(Relationship).where(
            Relationship.source_asset_id == source_asset_id,
            Relationship.target_asset_id == target_asset_id,
            Relationship.relationship_type == relationship_type,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def delete(self, session: AsyncSession, relationship: Relationship) -> None:
        """
        Hard-delete a relationship from the database.

        Unlike assets (which have an 'archived' soft-delete status),
        relationships are simply deleted. There's no meaningful
        "archived relationship" concept.
        """
        await session.delete(relationship)
        await session.flush()


# Singleton instance — import this in the service layer
relationship_repository = RelationshipRepository()
