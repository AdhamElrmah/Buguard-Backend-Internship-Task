import pytest


@pytest.mark.asyncio
async def test_public_read_endpoints(client):
    """
    Verify that read operations (GET) are public and do not require API key.
    """
    # GET assets list
    response = await client.get("/api/v1/assets")
    assert response.status_code == 200

    # GET relationships list for non-existent asset should check path validation/not found
    # but doesn't block on auth (returns 404 since asset doesn't exist)
    response = await client.get(
        "/api/v1/assets/00000000-0000-0000-0000-000000000000/relationships"
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "not_found"


@pytest.mark.asyncio
async def test_write_endpoints_require_auth(client):
    """
    Verify that write operations (POST, PUT, PATCH, DELETE) fail with 401 when API key is missing.
    """
    # POST assets
    response = await client.post(
        "/api/v1/assets", json={"type": "domain", "value": "example.com"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "unauthorized"

    # POST bulk assets
    response = await client.post(
        "/api/v1/assets/bulk",
        json={"items": [{"type": "domain", "value": "example.com"}]},
    )
    assert response.status_code == 401

    # POST mark-stale
    response = await client.post(
        "/api/v1/assets/mark-stale", json={"threshold_days": 30}
    )
    assert response.status_code == 401

    # PUT asset
    response = await client.put(
        "/api/v1/assets/00000000-0000-0000-0000-000000000000",
        json={"type": "domain", "value": "example.com"},
    )
    assert response.status_code == 401

    # PATCH asset
    response = await client.patch(
        "/api/v1/assets/00000000-0000-0000-0000-000000000000", json={"value": "new.com"}
    )
    assert response.status_code == 401

    # DELETE asset
    response = await client.delete(
        "/api/v1/assets/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401

    # POST relationship
    response = await client.post(
        "/api/v1/relationships",
        json={
            "source_asset_id": "00000000-0000-0000-0000-000000000000",
            "target_asset_id": "00000000-0000-0000-0000-000000000000",
            "relationship_type": "belongs_to",
        },
    )
    assert response.status_code == 401

    # DELETE relationship
    response = await client.delete(
        "/api/v1/relationships/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_write_endpoints_invalid_key(client):
    """
    Verify that write operations fail with 403 when an invalid API key is provided.
    """
    headers = {"X-API-Key": "wrong_key"}

    # POST assets
    response = await client.post(
        "/api/v1/assets",
        json={"type": "domain", "value": "example.com"},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "forbidden"


@pytest.mark.asyncio
async def test_write_endpoints_valid_key(client, auth_headers):
    """
    Verify that write operations authenticate successfully with a valid API key.
    """
    response = await client.post(
        "/api/v1/assets",
        json={"type": "domain", "value": "example.com"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["value"] == "example.com"
