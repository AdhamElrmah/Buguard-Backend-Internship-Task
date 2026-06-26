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

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
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
        filters: "AssetFilters | None" = None,
    ) -> tuple[list[Asset], int]:
        """
        Fetch a paginated, filtered, sorted list of assets with total count.

        Builds a dynamic query based on the provided filters:
        - type: exact match on asset type
        - status: exact match on lifecycle status
        - tag: array containment — does the tags array include this value?
        - value: case-insensitive substring search (ILIKE)
        - sort_by / sort_order: ORDER BY clause
        - skip / limit: OFFSET / LIMIT for pagination

        Returns (assets, total_count). The total reflects the filtered
        count (not the entire table), so pagination math is correct.
        """
        from app.schemas.filters import AssetFilters  # avoid circular import

        # Start with a base query that selects all assets
        data_query = select(Asset)
        count_query = select(func.count()).select_from(Asset)

        # --- Apply filters ---
        # Each filter is optional. When present, it adds a WHERE clause.
        # Multiple filters combine with AND (each .where() call adds AND).
        if filters:
            if filters.type:
                data_query = data_query.where(Asset.type == filters.type)
                count_query = count_query.where(Asset.type == filters.type)

            if filters.status:
                data_query = data_query.where(Asset.status == filters.status)
                count_query = count_query.where(Asset.status == filters.status)

            if filters.tag:
                # PostgreSQL array containment: tags @> ARRAY['prod']
                # This checks if the tags column contains the given value.
                # The GIN index (idx_assets_tags) makes this fast.
                data_query = data_query.where(
                    Asset.tags.contains([filters.tag])
                )
                count_query = count_query.where(
                    Asset.tags.contains([filters.tag])
                )

            if filters.value:
                # ILIKE = case-insensitive LIKE
                # f"%{value}%" = substring match (contains)
                data_query = data_query.where(
                    Asset.value.ilike(f"%{filters.value}%")
                )
                count_query = count_query.where(
                    Asset.value.ilike(f"%{filters.value}%")
                )

            # --- Apply sorting ---
            # getattr(Asset, "created_at") returns the SQLAlchemy column object.
            # .asc() or .desc() sets the sort direction.
            sort_column = getattr(Asset, filters.sort_by.value)
            if filters.sort_order.value == "desc":
                data_query = data_query.order_by(sort_column.desc())
            else:
                data_query = data_query.order_by(sort_column.asc())

        # --- Apply pagination ---
        data_query = data_query.offset(skip).limit(limit)

        # Execute both queries
        result = await session.execute(data_query)
        assets = list(result.scalars().all())

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

    # ------------------------------------------------------------------
    # Lifecycle Operations
    # ------------------------------------------------------------------

    async def mark_stale(
        self, session: AsyncSession, cutoff: datetime
    ) -> int:
        """
        Bulk-update all active assets with last_seen older than cutoff to stale.

        Uses a single UPDATE ... WHERE query instead of loading every asset
        into Python memory. This is critical for performance — if there are
        100,000 active assets, loading them all just to set status='stale'
        would be extremely slow and memory-intensive.

        The SQL equivalent:
            UPDATE assets
            SET status = 'stale'
            WHERE status = 'active'
              AND last_seen < :cutoff

        Returns the number of affected rows (how many assets transitioned).
        """
        stmt = (
            update(Asset)
            .where(
                Asset.status == "active",
                Asset.last_seen < cutoff,
            )
            .values(status="stale")
        )
        result = await session.execute(stmt)

        # result.rowcount tells us how many rows were affected by the UPDATE.
        # This is a standard DBAPI attribute — PostgreSQL always returns it.
        return result.rowcount


# Singleton instance — import this in the service layer
asset_repository = AssetRepository()
