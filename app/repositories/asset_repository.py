"""
Data access layer for assets.

This module contains all database queries for the assets table.
It knows about SQLAlchemy models and sessions, but NOTHING about:
- HTTP requests/responses (that's the router's job)
- Business rules like deduplication (that's the service's job)
- Pydantic schemas (that's the schema's job)

Every method receives an AsyncSession from the caller (dependency injection),
so the repository never creates or manages its own sessions.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset


class AssetRepository:
    """
    Handles all database operations for the Asset model.

    Design: We use a class (not module-level functions) so that in tests,
    you could subclass or mock the repository to isolate the service layer.
    """

    async def create(self, session: AsyncSession, asset: Asset) -> Asset:
        """
        Insert a new asset into the database.

        The caller (service layer) is responsible for building the Asset object.
        We just add it to the session, flush to get the DB-generated defaults
        (like timestamps), and refresh to load the full object.
        """
        session.add(asset)
        await session.flush()
        await session.refresh(asset)
        return asset

    async def get_by_id(self, session: AsyncSession, asset_id: UUID) -> Asset | None:
        """
        Fetch a single asset by its primary key.

        Returns None if not found — the service layer decides whether
        that's a 404 error or a normal "doesn't exist" check.
        """
        return await session.get(Asset, asset_id)

    async def get_by_type_and_value(
        self, session: AsyncSession, asset_type: str, value: str
    ) -> Asset | None:
        """
        Look up an asset by its deduplication key (type + value).

        Used by the deduplication logic in the service layer to check
        if an asset already exists before creating a new one.
        """
        query = select(Asset).where(Asset.type == asset_type, Asset.value == value)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        session: AsyncSession,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Asset], int]:
        """
        Fetch a paginated list of assets with total count.

        Returns a tuple of (assets, total_count) so the router can
        build a paginated response. Filtering and sorting will be
        added in Milestone 5.

        Why two queries?
        - The data query uses OFFSET/LIMIT for pagination
        - The count query gets the total (ignoring pagination)
        The client needs both: the page of data AND the total to
        calculate how many pages exist.
        """
        # Data query
        data_query = select(Asset).offset(skip).limit(limit)
        result = await session.execute(data_query)
        assets = list(result.scalars().all())

        # Count query
        count_query = select(func.count()).select_from(Asset)
        total = await session.scalar(count_query)

        return assets, total

    async def update(self, session: AsyncSession, asset: Asset) -> Asset:
        """
        Persist changes to an existing asset.

        The caller modifies the Asset object's attributes directly,
        then calls this method. flush() sends the UPDATE to the DB,
        and refresh() reloads the object with any DB-side changes
        (like the updated_at timestamp from onupdate).
        """
        await session.flush()
        await session.refresh(asset)
        return asset

    async def delete(self, session: AsyncSession, asset: Asset) -> None:
        """
        Hard-delete an asset from the database.

        ON DELETE CASCADE on the relationships table means all
        relationships involving this asset are automatically removed.
        """
        await session.delete(asset)
        await session.flush()


# Singleton instance — import this in the service layer
asset_repository = AssetRepository()
