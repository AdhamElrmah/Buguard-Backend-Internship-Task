"""
SQLAlchemy ORM model for the relationships table.

A relationship is a **directed edge** between two assets.
Think of it like an arrow: source_asset → target_asset.

Examples:
    subdomain "api.example.com"  → belongs_to → domain "example.com"
    service "nginx:443"          → runs_on    → ip_address "10.0.0.1"
    certificate "*.example.com"  → secures    → domain "example.com"

Key design decisions:
    - Directed: source and target are distinct (A→B ≠ B→A).
    - relationship_type as VARCHAR (not PG ENUM): adding new types
      doesn't require a database migration. The enum is enforced in
      the Pydantic schema layer instead.
    - ON DELETE CASCADE on both FKs: deleting an asset automatically
      removes all relationships where it appears as source OR target.
      This prevents orphaned relationship rows.
    - UNIQUE(source, target, type): prevents creating the exact same
      relationship twice. You can have multiple relationship types
      between the same pair of assets (e.g., "runs_on" AND "depends_on").
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Relationship(Base):
    """Represents a directed relationship between two assets."""

    __tablename__ = "relationships"

    # --- Primary Key ---
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # --- Foreign Keys ---
    # source_asset_id: the "from" side of the relationship.
    # ON DELETE CASCADE means: if this asset is deleted from the assets
    # table, all relationships where it is the source are auto-deleted.
    source_asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )

    # target_asset_id: the "to" side of the relationship.
    # Same CASCADE behavior as source_asset_id.
    target_asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- Relationship Type ---
    # Stored as plain VARCHAR, not a PostgreSQL ENUM type.
    # Why? Adding a new relationship type to a PG ENUM requires
    # an ALTER TYPE migration, which is painful and can lock tables.
    # VARCHAR lets us add new types by simply updating the Python enum.
    relationship_type = Column(String(50), nullable=False)

    # --- Timestamp ---
    # Only created_at — relationships don't have "updates".
    # If you need to change a relationship, you delete and recreate it.
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # --- Table-Level Constraints & Indexes ---
    __table_args__ = (
        # Prevent duplicate relationships: the same source → target
        # with the same type can only exist once.
        UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "relationship_type",
            name="uq_rel_source_target_type",
        ),

        # B-tree indexes for fast lookups by either side of the edge.
        # "Find all relationships FROM asset X" → uses idx_rel_source.
        # "Find all relationships TO asset X"   → uses idx_rel_target.
        Index("idx_rel_source", "source_asset_id"),
        Index("idx_rel_target", "target_asset_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Relationship(id={self.id}, "
            f"source={self.source_asset_id}, "
            f"target={self.target_asset_id}, "
            f"type={self.relationship_type})>"
        )
