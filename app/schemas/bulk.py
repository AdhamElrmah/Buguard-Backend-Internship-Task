"""
Pydantic schemas for bulk asset import.

The bulk import endpoint uses a "partial success" model:
- Each asset in the list is processed independently.
- Valid assets are created; invalid ones are collected into an error report.
- The response tells the client exactly what succeeded and what failed.

This is the industry-standard approach for import endpoints.
You don't want 999 valid rows rejected because row 1000 had a typo.
"""

from pydantic import BaseModel, Field

from app.schemas.asset import AssetCreate, AssetResponse


class BulkAssetCreate(BaseModel):
    """
    Request body for POST /api/v1/assets/bulk.

    Contains a list of assets to import. Each item uses the same
    validation rules as the single-create endpoint (AssetCreate).

    Example request body:
    {
        "items": [
            {"type": "domain", "value": "example.com"},
            {"type": "ip_address", "value": "192.168.1.1"},
            {"type": "invalid_type", "value": "bad"}   ← this one will fail
        ]
    }
    """
    items: list[AssetCreate] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of assets to import (1–1000 items per request)",
    )


class BulkImportError(BaseModel):
    """
    Details about a single failed item during bulk import.

    'index' tells the client which item in their list failed,
    so they can fix and re-submit just the problematic items.
    """
    index: int = Field(
        ..., description="0-based index of the failed item in the request list"
    )
    value: str = Field(
        ..., description="The 'value' field of the failed item (for easy identification)"
    )
    error: str = Field(
        ..., description="Human-readable error message explaining why it failed"
    )


class BulkImportResponse(BaseModel):
    """
    Response for the bulk import endpoint.

    Provides a summary of the operation plus detailed error reports
    for any items that failed. The client can check:
    - failed == 0  → complete success
    - failed > 0   → partial success, inspect 'errors' for details

    Example response:
    {
        "total_received": 10,
        "successful": 8,
        "failed": 2,
        "errors": [
            {"index": 3, "value": "bad-asset", "error": "Invalid asset type"},
            {"index": 7, "value": "dup.com", "error": "Asset already exists"}
        ],
        "assets": [ ...8 created assets... ]
    }
    """
    total_received: int = Field(
        ..., description="Total number of items received in the request"
    )
    successful: int = Field(
        ..., description="Number of assets successfully created"
    )
    failed: int = Field(
        ..., description="Number of assets that failed to import"
    )
    errors: list[BulkImportError] = Field(
        default_factory=list,
        description="Details about each failed item",
    )
    assets: list[AssetResponse] = Field(
        default_factory=list,
        description="List of successfully created assets",
    )
