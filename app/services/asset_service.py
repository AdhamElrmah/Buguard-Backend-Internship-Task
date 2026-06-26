"""
Business logic layer for assets.

This module sits between the router (HTTP) and the repository (database).
It handles:
- Converting Pydantic schemas → SQLAlchemy models (and vice versa)
- Raising appropriate errors (404, 409, etc.)
- Business rules: deduplication, tag merging, metadata merging

The service NEVER touches the HTTP request/response directly.
It receives typed data (Pydantic schemas) and returns typed data.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.repositories.asset_repository import asset_repository
from app.schemas.asset import (
    AssetCreate,
    AssetListResponse,
    AssetPatch,
    AssetResponse,
    AssetUpdate,
    MarkStaleResponse,
)
from app.schemas.bulk import BulkImportError, BulkImportResponse


class AssetService:
    """
    Business logic for asset operations.

    Why a class instead of plain functions?
    - The service depends on the repository. Using a class makes this
      dependency explicit and easy to swap in tests.
    - As the project grows, shared state (like config or caching) can
      live on the instance.
    """

    def __init__(self):
        self.repo = asset_repository

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    async def _handle_dedup(
        self, session: AsyncSession, data: AssetCreate
    ) -> Asset:
        """
        Core deduplication logic used by both create_asset() and bulk_import().

        Dedup key: (type, value). If an asset with the same type+value
        already exists, we MERGE instead of creating a duplicate.

        Merge rules:
        ┌─────────────┬──────────────────────────────────────────────────┐
        │ Field       │ Behavior                                        │
        ├─────────────┼──────────────────────────────────────────────────┤
        │ first_seen  │ NEVER changed (immutable after creation)        │
        │ last_seen   │ Always updated to now                           │
        │ tags        │ Union of old + new (no duplicates)              │
        │ metadata    │ Shallow merge: {**old, **new}                   │
        │ status      │ If existing is 'stale' → transition to 'active' │
        │ source      │ Kept as-is (original discovery source)          │
        └─────────────┴──────────────────────────────────────────────────┘

        Why shallow merge for metadata?
        Deep merge is ambiguous — what if both old and new have nested
        objects with conflicting keys? Shallow merge is predictable:
        new keys overwrite old keys at the top level, old keys that
        don't exist in new are preserved.

        Returns the Asset object (either newly created or updated existing).
        The caller is responsible for committing the transaction.
        """
        now = datetime.now(timezone.utc)

        # Step 1: Check if an asset with this (type, value) already exists
        existing = await self.repo.get_by_type_and_value(
            session, data.type.value, data.value
        )

        if existing:
            # --- MERGE with existing asset ---

            # last_seen: always update to the current time (now) during deduplication
            existing.last_seen = now

            # tags: union of old + new, removing duplicates
            # set() automatically handles deduplication
            # Example: old=["prod", "web"], new=["web", "api"] → ["prod", "web", "api"]
            merged_tags = list(set(existing.tags or []) | set(data.tags or []))
            existing.tags = merged_tags

            # metadata: shallow merge — new keys overwrite, old keys preserved
            # Example: old={"port": 443}, new={"protocol": "https"}
            #        → {"port": 443, "protocol": "https"}
            merged_metadata = {**(existing.metadata_ or {}), **(data.metadata or {})}
            existing.metadata_ = merged_metadata

            # status: re-sighting rule
            # If the asset was marked 'stale' (not seen for a while) and
            # we're seeing it again, transition back to 'active'.
            # IMPORTANT: 'archived' assets are NOT auto-reactivated.
            # Archiving is a deliberate human decision.
            if existing.status == "stale":
                existing.status = "active"

            # first_seen: NEVER change. This is the immutable "birth date"
            # of the asset. Even if the new data has a different first_seen,
            # we ignore it.

            # source: keep the original source (how it was first discovered)

            asset = await self.repo.update(session, existing)
            return asset

        else:
            # --- CREATE new asset ---
            asset = Asset(
                type=data.type.value,
                value=data.value,
                status=data.status.value,
                source=data.source.value,
                tags=data.tags,
                metadata_=data.metadata,
                first_seen=now,
                last_seen=now,
            )

            asset = await self.repo.create(session, asset)
            return asset

    # ------------------------------------------------------------------
    # CRUD Operations
    # ------------------------------------------------------------------

    async def create_asset(
        self, session: AsyncSession, data: AssetCreate
    ) -> AssetResponse:
        """
        Create a new asset, or merge with existing if duplicate.

        Uses _handle_dedup() to check for existing assets with the same
        (type, value) pair. If found, merges tags/metadata/timestamps
        instead of raising a duplicate error.
        """
        asset = await self._handle_dedup(session, data)
        await session.commit()
        return AssetResponse.model_validate(asset)

    async def get_asset(self, session: AsyncSession, asset_id: UUID) -> AssetResponse:
        """
        Retrieve a single asset by ID.

        Raises 404 if the asset doesn't exist. This is a business decision:
        the repository returns None (neutral), the service decides that
        "not found" is an error in this context.
        """
        asset = await self.repo.get_by_id(session, asset_id)
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset with id '{asset_id}' not found",
            )
        return AssetResponse.model_validate(asset)

    async def list_assets(
        self,
        session: AsyncSession,
        filters: "AssetFilters",
    ) -> AssetListResponse:
        """
        List assets with filtering, sorting, and pagination.

        The filters object contains all query parameters (type, status,
        tag, value, sort_by, sort_order, page, page_size). The service
        extracts pagination values and passes everything to the repository.
        """
        from app.schemas.filters import AssetFilters  # avoid circular import

        skip = (filters.page - 1) * filters.page_size
        assets, total = await self.repo.get_all(
            session, skip=skip, limit=filters.page_size, filters=filters
        )

        return AssetListResponse(
            items=[AssetResponse.model_validate(a) for a in assets],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    async def update_asset(
        self, session: AsyncSession, asset_id: UUID, data: AssetUpdate
    ) -> AssetResponse:
        """
        Full replacement of an asset (PUT semantics).

        PUT means "replace the entire resource". Every field in the
        request body overwrites the existing value. If a field is omitted,
        it gets the schema's default value — this is correct PUT behavior.
        """
        asset = await self.repo.get_by_id(session, asset_id)
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset with id '{asset_id}' not found",
            )

        asset.type = data.type.value
        asset.value = data.value
        asset.status = data.status.value
        asset.source = data.source.value
        asset.tags = data.tags
        asset.metadata_ = data.metadata
        asset = await self.repo.update(session, asset)
        await session.commit()
        return AssetResponse.model_validate(asset)

    async def patch_asset(
        self, session: AsyncSession, asset_id: UUID, data: AssetPatch
    ) -> AssetResponse:
        """
        Partial update of an asset (PATCH semantics).

        PATCH means "update only the fields that are provided".
        We use exclude_unset=True to get ONLY the fields the client
        actually sent in the request body. Fields not sent are left unchanged.

        Example: PATCH with {"status": "stale"} only updates status,
        leaving type, value, tags, etc. untouched.
        """
        asset = await self.repo.get_by_id(session, asset_id)
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset with id '{asset_id}' not found",
            )

        # model_dump(exclude_unset=True) is the key to PATCH semantics.
        # It returns ONLY the fields the client included in the request.
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "metadata":
                # Map API's 'metadata' to SQLAlchemy's 'metadata_'
                setattr(asset, "metadata_", value)
            elif field in ("type", "status", "source") and value is not None:
                # Enum fields: store the string value, not the enum object
                setattr(asset, field, value.value if hasattr(value, "value") else value)
            else:
                setattr(asset, field, value)

        asset = await self.repo.update(session, asset)
        await session.commit()
        return AssetResponse.model_validate(asset)

    async def bulk_import(
        self, session: AsyncSession, items: list[AssetCreate]
    ) -> BulkImportResponse:
        """
        Import multiple assets at once (partial success model).

        Each asset is processed independently using _handle_dedup():
        - If the asset is new → create it.
        - If it already exists → merge (update tags, metadata, last_seen).
        - If something fails → record the error, continue with next item.

        Why partial success instead of all-or-nothing?
        - Import endpoints commonly receive hundreds of items.
        - Rejecting everything because one item is bad is a poor UX.
        - The response tells the client exactly what failed and why,
          so they can fix and re-submit only the failures.
        """
        created_assets: list[AssetResponse] = []
        errors: list[BulkImportError] = []

        for index, item in enumerate(items):
            try:
                # _handle_dedup creates new assets OR merges with existing ones.
                # Either way, it returns a valid Asset object.
                asset = await self._handle_dedup(session, item)

                # flush() sends the INSERT/UPDATE to the database WITHOUT committing.
                # This lets us catch DB errors per-item.
                await session.flush()

                created_assets.append(AssetResponse.model_validate(asset))

            except Exception as e:
                # Something went wrong with this specific item.
                # Roll back just this item's changes and record the error.
                await session.rollback()
                errors.append(
                    BulkImportError(
                        index=index,
                        value=item.value,
                        error=str(e),
                    )
                )

        # Commit all successful assets in one transaction.
        if created_assets:
            await session.commit()

        return BulkImportResponse(
            total_received=len(items),
            successful=len(created_assets),
            failed=len(errors),
            errors=errors,
            assets=created_assets,
        )

    async def delete_asset(self, session: AsyncSession, asset_id: UUID) -> None:
        """
        Hard-delete an asset.

        The ON DELETE CASCADE constraint on the relationships table
        ensures related relationships are automatically removed.
        """
        asset = await self.repo.get_by_id(session, asset_id)
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset with id '{asset_id}' not found",
            )

        await self.repo.delete(session, asset)
        await session.commit()

    # ------------------------------------------------------------------
    # Lifecycle Operations
    # ------------------------------------------------------------------

    async def mark_stale(
        self, session: AsyncSession, threshold_days: int
    ) -> MarkStaleResponse:
        """
        Mark all active assets as stale if not seen within threshold_days.

        How it works:
        1. Calculate a cutoff datetime: now - threshold_days
           Example: if threshold_days=30 and today is June 26,
                    cutoff = May 27. Any active asset with last_seen
                    before May 27 becomes stale.
        2. Run a single bulk UPDATE query (no per-row loading).
        3. Return the count of affected assets.

        Why a single SQL UPDATE instead of loading assets one by one?
        - Performance: one query handles any number of assets.
        - Atomicity: all transitions happen in one transaction.
        - Memory: no need to load thousands of Asset objects into Python.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=threshold_days)

        affected = await self.repo.mark_stale(session, cutoff)
        await session.commit()

        return MarkStaleResponse(affected=affected)


# Singleton instance — import this in the router
asset_service = AssetService()
