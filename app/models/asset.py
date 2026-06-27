"""
SQLAlchemy ORM model for the assets table.

This maps the Python Asset class to the PostgreSQL 'assets' table.
Every column defined here becomes a database column; every Index
and UniqueConstraint becomes a database-level constraint.

Key design notes:
- UUID primary key: globally unique, no sequential guessing
- tags as TEXT[]: PostgreSQL array type with GIN index for fast containment queries
- metadata_ (not metadata): 'metadata' is reserved by SQLAlchemy's Base class
- UNIQUE(type, value): the deduplication key — two assets with the same
  type and value are considered the same asset
- Four timestamps: first_seen/last_seen (observation) vs created_at/updated_at (record)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from app.core.database import Base


class Asset(Base):
    """Represents an internet-facing asset tracked by DarkAtlas."""

    __tablename__ = "assets"

    # --- Primary Key ---
    # UUID v4: generated in Python, not by the database.
    # This avoids DB round-trips to get the ID after insert.
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # --- Core Fields ---
    # type: what kind of asset (domain, subdomain, ip_address, etc.)
    # Stored as VARCHAR in the DB; validated as an enum in Pydantic schemas.
    type = Column(String(50), nullable=False, index=True)

    # value: the actual identifier (e.g., "example.com", "192.168.1.1")
    # VARCHAR(2048) accommodates long URLs and certificate subjects.
    value = Column(String(2048), nullable=False, index=True)

    # status: lifecycle state (active, stale, archived)
    status = Column(String(20), nullable=False, default="active", index=True)

    # source: how this asset was discovered (manual, scan, import)
    source = Column(String(20), nullable=False, default="manual")

    # --- Flexible Fields ---
    # tags: free-form labels for filtering and grouping.
    # PostgreSQL TEXT[] with GIN index enables fast queries like:
    #   WHERE tags @> ARRAY['prod', 'critical']
    tags = Column(ARRAY(Text), nullable=False, default=list)

    # metadata_: arbitrary key-value data (e.g., {"port": 443, "protocol": "https"}).
    # Named metadata_ because 'metadata' is reserved by SQLAlchemy's DeclarativeBase.
    # JSONB supports indexing and efficient queries.
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)

    # --- Observation Timestamps ---
    # first_seen: when the asset was FIRST OBSERVED in the real world.
    #   Set on creation, never updated afterwards (immutable — enforced in service layer).
    # last_seen: when the asset was LAST OBSERVED.
    #   Updated every time the asset is re-imported or re-sighted.
    first_seen = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_seen = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # --- Record Timestamps ---
    # created_at: when this DATABASE ROW was created. Immutable.
    # updated_at: when this DATABASE ROW was last modified. Auto-updates.
    # These differ from first_seen/last_seen:
    #   Example: bulk-importing yesterday's scan → first_seen=yesterday, created_at=now
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # --- Table-Level Constraints & Indexes ---
    __table_args__ = (
        # Deduplication key: no two assets can have the same (type, value) pair.
        # This is how we detect duplicates during import.
        UniqueConstraint("type", "value", name="uq_assets_type_value"),
        # GIN index on tags for fast array containment queries.
        # Without this, `WHERE tags @> ARRAY['prod']` would require a full table scan.
        Index("idx_assets_tags", "tags", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Asset(id={self.id}, type={self.type}, value={self.value}, status={self.status})>"
