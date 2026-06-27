"""
Database Population Script

This script clears the database (using TRUNCATE CASCADE) and populates it with a rich set
of mock assets and relationships via the FastAPI application's API endpoints.

This allows you to immediately test all API operations (CRUD, filtering, sorting, pagination,
relationships, graph queries, lifecycle updates) in the interactive Swagger UI.

Usage:
    python populate_db.py
"""

import asyncio
import os
from typing import Dict
from uuid import UUID

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

# Load environment variables
load_dotenv()

# We import the ASGI app so we can run requests in-process without needing
# the server to be running separately.
from app.main import app  # noqa: E402
from app.core.database import engine  # noqa: E402

# Rich mock assets to import
MOCK_ASSETS = [
    # Domains & Subdomains
    {
        "type": "domain",
        "value": "example.com",
        "status": "active",
        "source": "scan",
        "tags": ["root", "scope-in"],
        "metadata": {"registrar": "Namecheap", "dnssec": "disabled"},
    },
    {
        "type": "subdomain",
        "value": "api.example.com",
        "status": "active",
        "source": "scan",
        "tags": ["prod", "api"],
        "metadata": {"stage": "production", "public": True, "provider": "AWS"},
    },
    {
        "type": "subdomain",
        "value": "staging.example.com",
        "status": "active",
        "source": "scan",
        "tags": ["staging"],
        "metadata": {"stage": "staging", "public": False, "provider": "AWS"},
    },
    {
        "type": "subdomain",
        "value": "dev.example.com",
        "status": "active",
        "source": "scan",
        "tags": ["dev"],
        "metadata": {"stage": "development", "public": False, "provider": "Local"},
    },
    {
        "type": "subdomain",
        "value": "old.example.com",
        "status": "stale",
        "source": "manual",
        "tags": ["legacy"],
        "metadata": {"stage": "deprecated", "last_active": "2025-12-01"},
    },
    {
        "type": "subdomain",
        "value": "hidden.example.com",
        "status": "archived",
        "source": "manual",
        "tags": ["decommissioned"],
        "metadata": {"reason": "dns-removed", "decom_date": "2026-01-15"},
    },
    # IP Addresses
    {
        "type": "ip_address",
        "value": "93.184.216.34",
        "status": "active",
        "source": "scan",
        "tags": ["prod", "cdn"],
        "metadata": {"country": "US", "asn": 15133, "provider": "Edgecast"},
    },
    {
        "type": "ip_address",
        "value": "192.168.1.100",
        "status": "active",
        "source": "manual",
        "tags": ["internal", "staging"],
        "metadata": {"subnet": "office", "restricted": True},
    },
    # Services
    {
        "type": "service",
        "value": "443/tcp",
        "status": "active",
        "source": "scan",
        "tags": ["ssl", "prod"],
        "metadata": {"banner": "nginx/1.24.0", "tls": "TLSv1.3", "ports": [443]},
    },
    {
        "type": "service",
        "value": "80/tcp",
        "status": "stale",
        "source": "scan",
        "tags": ["http"],
        "metadata": {"banner": "nginx/1.24.0", "ports": [80]},
    },
    {
        "type": "service",
        "value": "8080/tcp",
        "status": "active",
        "source": "scan",
        "tags": ["staging", "http"],
        "metadata": {"banner": "Apache/2.4.58 (Unix)", "ports": [8080]},
    },
    # Certificates
    {
        "type": "certificate",
        "value": "CN=api.example.com",
        "status": "active",
        "source": "scan",
        "tags": ["prod", "ssl"],
        "metadata": {
            "issuer": "Let's Encrypt",
            "expires": "2025-01-02",
            "expired": True,
        },
    },
    {
        "type": "certificate",
        "value": "CN=staging.example.com",
        "status": "active",
        "source": "scan",
        "tags": ["staging", "ssl"],
        "metadata": {
            "issuer": "Let's Encrypt",
            "expires": "2026-12-31",
            "expired": False,
        },
    },
    # Technologies
    {
        "type": "technology",
        "value": "nginx",
        "status": "active",
        "source": "scan",
        "tags": ["web-server", "oss"],
        "metadata": {"version": "1.24.0", "cve_count": 0},
    },
    {
        "type": "technology",
        "value": "apache",
        "status": "active",
        "source": "scan",
        "tags": ["web-server", "oss"],
        "metadata": {"version": "2.4.58", "cve_count": 2},
    },
]

# Directed relationships to establish
MOCK_RELATIONSHIPS = [
    # Subdomains to Domain
    ("subdomain", "api.example.com", "belongs_to", "domain", "example.com"),
    ("subdomain", "staging.example.com", "belongs_to", "domain", "example.com"),
    ("subdomain", "dev.example.com", "belongs_to", "domain", "example.com"),
    ("subdomain", "old.example.com", "belongs_to", "domain", "example.com"),
    ("subdomain", "hidden.example.com", "belongs_to", "domain", "example.com"),
    # Subdomains to IPs
    ("subdomain", "api.example.com", "resolves_to", "ip_address", "93.184.216.34"),
    ("subdomain", "staging.example.com", "resolves_to", "ip_address", "192.168.1.100"),
    # Services to IPs
    ("service", "443/tcp", "runs_on", "ip_address", "93.184.216.34"),
    ("service", "80/tcp", "runs_on", "ip_address", "93.184.216.34"),
    ("service", "8080/tcp", "runs_on", "ip_address", "192.168.1.100"),
    # Certificates to Subdomains
    ("certificate", "CN=api.example.com", "secures", "subdomain", "api.example.com"),
    (
        "certificate",
        "CN=staging.example.com",
        "secures",
        "subdomain",
        "staging.example.com",
    ),
    # Technologies to Subdomains
    ("technology", "nginx", "connected_to", "subdomain", "api.example.com"),
    ("technology", "apache", "connected_to", "subdomain", "staging.example.com"),
]


async def clear_database():
    """Truncates all tables in the database to start fresh."""
    print("Clearing database tables...")
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE relationships, assets CASCADE;"))
    print("Database cleared successfully.")


async def populate():
    # 1. Clear database
    await clear_database()

    # 2. Get API key from env
    api_key = os.getenv("API_KEY", "testing")
    headers = {"X-API-Key": api_key}
    print(f"Using API Key: '{api_key}'")

    # We use httpx AsyncClient in-process to hit the ASGI application directly
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost:8000"
    ) as client:
        # 3. Bulk import assets
        print("\nImporting assets...")
        bulk_payload = {"items": MOCK_ASSETS}
        response = await client.post(
            "/api/v1/assets/bulk", json=bulk_payload, headers=headers
        )

        if response.status_code != 200:
            print(f"Error during bulk import: {response.status_code} - {response.text}")
            return

        import_data = response.json()
        print(
            f"Assets import summary: total={import_data['total_received']}, "
            f"successful={import_data['successful']}, failed={import_data['failed']}"
        )

        # Map each (type, value) to its generated database UUID
        asset_map: Dict[tuple, UUID] = {}
        for asset in import_data["assets"]:
            key = (asset["type"], asset["value"])
            asset_map[key] = asset["id"]

        # 4. Create relationships
        print("\nCreating directed relationships...")
        created_relations_count = 0

        for src_type, src_val, rel_type, tgt_type, tgt_val in MOCK_RELATIONSHIPS:
            src_id = asset_map.get((src_type, src_val))
            tgt_id = asset_map.get((tgt_type, tgt_val))

            if not src_id or not tgt_id:
                print(
                    f"Skipping relationship {src_val} --[{rel_type}]--> {tgt_val} (asset missing)"
                )
                continue

            rel_payload = {
                "source_asset_id": src_id,
                "target_asset_id": tgt_id,
                "relationship_type": rel_type,
            }

            rel_resp = await client.post(
                "/api/v1/relationships", json=rel_payload, headers=headers
            )
            if rel_resp.status_code == 201:
                created_relations_count += 1
            else:
                print(
                    f"Failed to create relationship: {src_val} -> {tgt_val}. Status: {rel_resp.status_code}"
                )

        print(
            f"Relationships created successfully: {created_relations_count}/{len(MOCK_RELATIONSHIPS)}"
        )
        print("\n=== Populating Database Complete ===")
        print(
            "You can now open http://localhost:8000/docs to explore and query the mock dataset!"
        )


if __name__ == "__main__":
    asyncio.run(populate())
