import pytest
from uuid import uuid4

@pytest.mark.asyncio
async def test_asset_crud_flow(client, auth_headers):
    """
    Test the full CRUD flow for a single asset: Create, Read, Update, Patch, and Delete.
    """
    # 1. Create Asset
    create_payload = {
        "type": "domain",
        "value": "buguard.io",
        "status": "active",
        "source": "manual",
        "tags": ["prod", "web"],
        "metadata": {"owner": "buguard"}
    }
    response = await client.post("/api/v1/assets", json=create_payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "domain"
    assert data["value"] == "buguard.io"
    assert data["tags"] == ["prod", "web"]
    assert data["metadata"] == {"owner": "buguard"}
    asset_id = data["id"]
    assert asset_id is not None

    # 2. Read Asset
    response = await client.get(f"/api/v1/assets/{asset_id}")
    assert response.status_code == 200
    assert response.json()["id"] == asset_id

    # 3. Read Asset Not Found
    fake_id = str(uuid4())
    response = await client.get(f"/api/v1/assets/{fake_id}")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "not_found"

    # 4. Update Asset (PUT - full replacement)
    update_payload = {
        "type": "subdomain",
        "value": "blog.buguard.io",
        "status": "stale",
        "source": "scan",
        "tags": ["blog"],
        "metadata": {"updated": True}
    }
    response = await client.put(f"/api/v1/assets/{asset_id}", json=update_payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "subdomain"
    assert data["value"] == "blog.buguard.io"
    assert data["status"] == "stale"
    assert data["tags"] == ["blog"]
    assert data["metadata"] == {"updated": True}

    # 5. Patch Asset (PATCH - partial replacement)
    patch_payload = {
        "status": "active",
        "tags": ["blog", "marketing"]
    }
    response = await client.patch(f"/api/v1/assets/{asset_id}", json=patch_payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "subdomain"  # Unchanged
    assert data["status"] == "active"   # Updated
    assert data["tags"] == ["blog", "marketing"] # Updated

    # 6. Delete Asset
    response = await client.delete(f"/api/v1/assets/{asset_id}", headers=auth_headers)
    assert response.status_code == 204

    # 7. Verify Deleted
    response = await client.get(f"/api/v1/assets/{asset_id}")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_asset_list_filtering(client, auth_headers):
    """
    Test filtering of assets by type, status, tag, and value substring.
    """
    # Create test assets
    assets = [
        {"type": "domain", "value": "google.com", "status": "active", "tags": ["search", "corp"]},
        {"type": "domain", "value": "youtube.com", "status": "active", "tags": ["video", "corp"]},
        {"type": "ip_address", "value": "8.8.8.8", "status": "stale", "tags": ["dns", "google"]},
        {"type": "service", "value": "ssh://1.1.1.1", "status": "archived", "tags": ["infra"]}
    ]
    for asset in assets:
        resp = await client.post("/api/v1/assets", json=asset, headers=auth_headers)
        assert resp.status_code == 201

    # Filter by type
    response = await client.get("/api/v1/assets?type=domain")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all(item["type"] == "domain" for item in data["items"])

    # Filter by status
    response = await client.get("/api/v1/assets?status=stale")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["value"] == "8.8.8.8"

    # Filter by tag
    response = await client.get("/api/v1/assets?tag=corp")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert {item["value"] for item in data["items"]} == {"google.com", "youtube.com"}

    # Filter by value substring
    response = await client.get("/api/v1/assets?value=tube")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["value"] == "youtube.com"

@pytest.mark.asyncio
async def test_asset_list_sorting_and_pagination(client, auth_headers):
    """
    Test sorting and pagination for list assets.
    """
    # Create 5 assets with incremental values to sort easily
    for i in range(1, 6):
        payload = {"type": "domain", "value": f"asset{i}.com", "status": "active"}
        resp = await client.post("/api/v1/assets", json=payload, headers=auth_headers)
        assert resp.status_code == 201

    # Test sorting by value ascending
    response = await client.get("/api/v1/assets?sort_by=value&sort_order=asc")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    values = [item["value"] for item in data["items"]]
    assert values == ["asset1.com", "asset2.com", "asset3.com", "asset4.com", "asset5.com"]

    # Test sorting by value descending
    response = await client.get("/api/v1/assets?sort_by=value&sort_order=desc")
    assert response.status_code == 200
    data = response.json()
    values = [item["value"] for item in data["items"]]
    assert values == ["asset5.com", "asset4.com", "asset3.com", "asset2.com", "asset1.com"]

    # Test pagination page=1, page_size=2
    response = await client.get("/api/v1/assets?sort_by=value&sort_order=asc&page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["value"] == "asset1.com"
    assert data["items"][1]["value"] == "asset2.com"

    # Test pagination page=2, page_size=2
    response = await client.get("/api/v1/assets?sort_by=value&sort_order=asc&page=2&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["value"] == "asset3.com"
    assert data["items"][1]["value"] == "asset4.com"
