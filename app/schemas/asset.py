"""
Pydantic schemas for asset request/response validation.

These are SEPARATE from the SQLAlchemy model (app/models/asset.py).
- Models define the DATABASE structure (what columns exist in PostgreSQL).
- Schemas define the API CONTRACT (what JSON the client sends/receives).

This separation lets us:
- Accept different fields on create vs update vs patch
- Hide internal fields (like metadata_ column name) from the API
- Add validation rules without touching the database schema
- Change the API response format without a database migration

Enum classes are defined here because they are part of the API contract.
The database stores them as plain VARCHAR strings.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- Enums ---
# We use (str, Enum) instead of StrEnum for Python 3.9+ compatibility.
# The str mixin makes enum values serialize as strings in JSON automatically.


class AssetType(str, Enum):
    """Valid asset types in the DarkAtlas platform."""
    DOMAIN = "domain"
    SUBDOMAIN = "subdomain"
    IP_ADDRESS = "ip_address"
    SERVICE = "service"
    CERTIFICATE = "certificate"
    TECHNOLOGY = "technology"


class AssetStatus(str, Enum):
    """
    Asset lifecycle states.

    active    → recently observed, currently relevant
    stale     → not seen for a while, may no longer exist
    archived  → manually marked inactive, kept for historical records
    """
    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"


class AssetSource(str, Enum):
    """How the asset was discovered or added to the system."""
    MANUAL = "manual"
    SCAN = "scan"
    IMPORT = "import"


# --- Request Schemas ---


class AssetCreate(BaseModel):
    """
    Schema for creating a new asset (POST request body).

    Only 'type' and 'value' are required — everything else has sensible defaults.
    This keeps the API easy to use: a minimal valid request is just:
      {"type": "domain", "value": "example.com"}
    """
    type: AssetType
    value: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="The asset identifier (e.g., domain name, IP address)",
    )
    status: AssetStatus = AssetStatus.ACTIVE
    source: AssetSource = AssetSource.MANUAL
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form labels for filtering and grouping",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value data about the asset",
    )
    first_seen: Optional[datetime] = Field(
        None,
        description="When the asset was first observed (defaults to now if not provided)",
    )
    last_seen: Optional[datetime] = Field(
        None,
        description="When the asset was last observed (defaults to now if not provided)",
    )


class AssetUpdate(BaseModel):
    """
    Schema for full asset replacement (PUT request body).

    All fields are required because PUT semantically means
    'replace the entire resource'. If the client omits a field,
    it would be set to its default — which is the correct PUT behavior.
    """
    type: AssetType
    value: str = Field(..., min_length=1, max_length=2048)
    status: AssetStatus = AssetStatus.ACTIVE
    source: AssetSource = AssetSource.MANUAL
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


class AssetPatch(BaseModel):
    """
    Schema for partial asset update (PATCH request body).

    ALL fields are Optional. Only the fields the client sends
    will be updated; everything else stays unchanged.
    This is the key difference from AssetUpdate (PUT).
    """
    type: Optional[AssetType] = None
    value: Optional[str] = Field(None, min_length=1, max_length=2048)
    status: Optional[AssetStatus] = None
    source: Optional[AssetSource] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


# --- Response Schemas ---


class AssetResponse(BaseModel):
    """
    Schema for returning an asset in API responses.

    model_config with from_attributes=True tells Pydantic to read data
    from SQLAlchemy model attributes (e.g., asset.type) instead of
    expecting a dictionary. This enables: AssetResponse.model_validate(db_asset)
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: AssetType
    value: str
    status: AssetStatus
    source: AssetSource
    tags: list[str]
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    first_seen: datetime
    last_seen: datetime
    created_at: datetime
    updated_at: datetime


class AssetListResponse(BaseModel):
    """
    Paginated list response for GET /api/v1/assets.

    Includes total count so the client can calculate total pages:
      total_pages = ceil(total / page_size)
    """
    items: list[AssetResponse]
    total: int
    page: int
    page_size: int
