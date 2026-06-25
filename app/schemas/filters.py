"""
Query parameter schemas for filtering, sorting, and pagination.

These are Pydantic models used to validate and parse query parameters
from the URL. FastAPI automatically extracts and validates them using
Depends().

Example URL:
  GET /api/v1/assets?type=domain&status=active&tag=prod&sort_by=created_at&sort_order=desc&page=1&page_size=20
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SortOrder(str, Enum):
    """Sort direction for query results."""
    ASC = "asc"
    DESC = "desc"


class SortField(str, Enum):
    """
    Allowed fields for sorting.

    We restrict sorting to specific fields rather than allowing
    arbitrary column names. This prevents:
    1. SQL injection (malicious column names)
    2. Performance issues (sorting on non-indexed columns)
    3. Information leakage (exposing internal column names)
    """
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    FIRST_SEEN = "first_seen"
    LAST_SEEN = "last_seen"
    VALUE = "value"
    TYPE = "type"
    STATUS = "status"


class AssetFilters(BaseModel):
    """
    Query parameters for filtering, sorting, and paginating assets.

    All fields are Optional — if not provided, no filter is applied
    for that field. Multiple filters combine with AND logic.

    Example: ?type=domain&status=active means
    WHERE type = 'domain' AND status = 'active'
    """

    # --- Filters ---
    type: Optional[str] = Field(
        None,
        description="Filter by asset type (e.g., domain, ip_address)",
    )
    status: Optional[str] = Field(
        None,
        description="Filter by asset status (e.g., active, stale, archived)",
    )
    tag: Optional[str] = Field(
        None,
        description="Filter by tag — returns assets whose tags array contains this value",
    )
    value: Optional[str] = Field(
        None,
        description="Search by value — case-insensitive substring match",
    )

    # --- Sorting ---
    sort_by: SortField = Field(
        SortField.CREATED_AT,
        description="Field to sort by",
    )
    sort_order: SortOrder = Field(
        SortOrder.DESC,
        description="Sort direction (asc or desc)",
    )

    # --- Pagination ---
    page: int = Field(
        1,
        ge=1,
        description="Page number (1-indexed)",
    )
    page_size: int = Field(
        20,
        ge=1,
        le=100,
        description="Number of items per page (max 100)",
    )
