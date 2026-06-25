"""
Business logic layer for assets.

This module sits between the router (HTTP) and the repository (database).
It handles:
- Converting Pydantic schemas → SQLAlchemy models (and vice versa)
- Raising appropriate errors (404, 409, etc.)
- Business rules (deduplication will be added in Milestone 7)

The service NEVER touches the HTTP request/response directly.
It receives typed data (Pydantic schemas) and returns typed data.
"""

from datetime import datetime, timezone
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

    async def create_asset(
        self, session: AsyncSession, data: AssetCreate
    ) -> AssetResponse:
        """
        Create a new asset.

        Converts the Pydantic schema to a SQLAlchemy model, saves it,
        and returns the response schema. The 'metadata' field from the
        API maps to 'metadata_' in the ORM model (because 'metadata'
        is reserved by SQLAlchemy's Base class).
        """
        now = datetime.now(timezone.utc)

        asset = Asset(
            type=data.type.value,
            value=data.value,
            status=data.status.value,
            source=data.source.value,
            tags=data.tags,
            metadata_=data.metadata,
            first_seen=data.first_seen or now,
            last_seen=data.last_seen or now,
        )

        asset = await self.repo.create(session, asset)
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
        if data.first_seen:
            asset.first_seen = data.first_seen
        if data.last_seen:
            asset.last_seen = data.last_seen

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

        Each asset is processed independently:
        - Valid assets are created and flushed to the database.
        - Invalid assets (e.g., duplicates) are collected into an error list.

        We flush (send SQL to DB) after each successful asset to detect
        database-level errors like unique constraint violations. But we
        only COMMIT once at the end — so either all successful assets
        are saved, or none are (if the final commit fails).

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
                now = datetime.now(timezone.utc)

                asset = Asset(
                    type=item.type.value,
                    value=item.value,
                    status=item.status.value,
                    source=item.source.value,
                    tags=item.tags,
                    metadata_=item.metadata,
                    first_seen=item.first_seen or now,
                    last_seen=item.last_seen or now,
                )

                asset = await self.repo.create(session, asset)

                # flush() sends the INSERT to the database WITHOUT committing.
                # This lets us catch DB errors (like unique violations) per-item.
                # If we only committed at the end, a single duplicate would
                # roll back ALL successfully created assets.
                await session.flush()

                created_assets.append(AssetResponse.model_validate(asset))

            except Exception as e:
                # Something went wrong with this specific item.
                # Roll back just this item's changes (expunge it from the session)
                # and record the error.
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


# Singleton instance — import this in the router
asset_service = AssetService()
