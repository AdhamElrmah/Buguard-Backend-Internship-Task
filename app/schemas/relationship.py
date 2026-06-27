"""
Pydantic schemas for relationship request/response validation.

Relationships are directed edges between two assets. The schemas here
define the API contract for creating and viewing relationships.

The RelationshipType enum is defined here (not in the model) because
the database stores it as a plain VARCHAR string. Validation happens
at the API layer — the database never rejects an invalid type.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.asset import AssetResponse


# --- Enums ---


class RelationshipType(str, Enum):
    """
    Valid relationship types between assets.

    Each type represents a directed connection:
        source_asset --[type]--> target_asset

    Examples:
        subdomain "api.example.com" --[belongs_to]--> domain "example.com"
        service "nginx:443"         --[runs_on]-----> ip_address "10.0.0.1"
        certificate "*.example.com" --[secures]-----> domain "example.com"
        domain "example.com"        --[resolves_to]-> ip_address "93.184.216.34"
        service "app:8080"          --[depends_on]--> service "db:5432"
        domain "example.com"        --[connected_to]> domain "partner.com"
    """

    BELONGS_TO = "belongs_to"
    RUNS_ON = "runs_on"
    SECURES = "secures"
    RESOLVES_TO = "resolves_to"
    DEPENDS_ON = "depends_on"
    CONNECTED_TO = "connected_to"


# --- Request Schemas ---


class RelationshipCreate(BaseModel):
    """
    Request body for creating a new relationship (POST).

    Both source and target must be valid asset UUIDs that already exist
    in the database. The service layer validates this before inserting.

    Self-referencing relationships (source == target) are rejected
    by the model_validator below — an asset cannot have a relationship
    with itself.
    """

    source_asset_id: UUID = Field(
        ...,
        description="UUID of the source asset (the 'from' side of the edge).",
    )
    target_asset_id: UUID = Field(
        ...,
        description="UUID of the target asset (the 'to' side of the edge).",
    )
    relationship_type: RelationshipType = Field(
        ...,
        description="The type of relationship between the two assets.",
    )

    @model_validator(mode="after")
    def validate_not_self_referencing(self) -> "RelationshipCreate":
        """
        Prevent an asset from having a relationship with itself.

        Why? Self-referencing edges are semantically meaningless in
        our domain. A domain cannot "belong to" itself or "resolve to"
        itself. Catching this early gives a clear error message instead
        of a confusing database state.
        """
        if self.source_asset_id == self.target_asset_id:
            raise ValueError(
                "source_asset_id and target_asset_id must be different — "
                "an asset cannot have a relationship with itself."
            )
        return self


# --- Response Schemas ---


class RelationshipResponse(BaseModel):
    """
    Response schema for returning a relationship in API responses.

    model_config with from_attributes=True allows Pydantic to read
    directly from the SQLAlchemy Relationship model object.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_asset_id: UUID
    target_asset_id: UUID
    relationship_type: RelationshipType
    created_at: datetime


class RelatedAsset(BaseModel):
    """
    Represents an asset connected to the queried asset,
    along with the connecting relationship details.
    """

    relationship_id: UUID
    relationship_type: RelationshipType
    direction: str  # "outgoing" or "incoming"
    asset: AssetResponse


class AssetGraphResponse(BaseModel):
    """
    Response schema for returning an asset along with all its related assets (the graph around it).
    """

    asset: AssetResponse
    relationships: list[RelatedAsset]
