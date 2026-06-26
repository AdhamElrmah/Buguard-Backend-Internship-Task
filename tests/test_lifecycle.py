import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import text

@pytest.mark.asyncio
async def test_lifecycle_mark_stale_endpoint(client, db, auth_headers):
    """
    Test bulk marking assets as stale based on last_seen threshold.
    """
    # 1. Create three assets
    asset_1 = {"type": "domain", "value": "old-active.com", "status": "active"}
    asset_2 = {"type": "domain", "value": "new-active.com", "status": "active"}
    asset_3 = {"type": "domain", "value": "archived.com", "status": "archived"}
    
    resp_1 = await client.post("/api/v1/assets", json=asset_1, headers=auth_headers)
    resp_2 = await client.post("/api/v1/assets", json=asset_2, headers=auth_headers)
    resp_3 = await client.post("/api/v1/assets", json=asset_3, headers=auth_headers)
    
    id_1 = resp_1.json()["id"]
    id_2 = resp_2.json()["id"]
    id_3 = resp_3.json()["id"]

    # 2. Manually backdate the last_seen for asset_1 (to 45 days ago) via raw SQL
    # This simulates it not being seen for a long time.
    old_time = datetime.now(timezone.utc) - timedelta(days=45)
    await db.execute(
        text("UPDATE assets SET last_seen = :old_time WHERE id = :id"),
        {"old_time": old_time, "id": id_1}
    )
    await db.commit()

    # 3. Call mark-stale with threshold of 30 days
    response = await client.post("/api/v1/assets/mark-stale", json={"threshold_days": 30}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["affected"] == 1 # Only old-active.com matches

    # 4. Verify statuses
    # old-active.com should be stale
    resp = await client.get(f"/api/v1/assets/{id_1}")
    assert resp.json()["status"] == "stale"

    # new-active.com should still be active
    resp = await client.get(f"/api/v1/assets/{id_2}")
    assert resp.json()["status"] == "active"

    # archived.com should remain archived (archived assets are never auto-staled/touched)
    resp = await client.get(f"/api/v1/assets/{id_3}")
    assert resp.json()["status"] == "archived"

@pytest.mark.asyncio
async def test_mark_stale_validation(client, auth_headers):
    """
    Verify that mark-stale returns 422 with a custom ValidationException
    if threshold_days is less than or equal to 0.
    """
    response = await client.post("/api/v1/assets/mark-stale", json={"threshold_days": 0}, headers=auth_headers)
    assert response.status_code == 422
    data = response.json()
    assert data["detail"]["error"] == "validation_error"
    assert "positive integer" in data["detail"]["message"]

    response = await client.post("/api/v1/assets/mark-stale", json={"threshold_days": -10}, headers=auth_headers)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_lifecycle_re_sighting_and_archived_protection(client, auth_headers):
    """
    Verify re-sighting transitions:
    - stale -> active on re-import
    - archived stays archived (never reactivates automatically)
    """
    # 1. Create a stale asset
    payload_stale = {"type": "domain", "value": "stale-asset.com", "status": "stale"}
    resp_stale = await client.post("/api/v1/assets", json=payload_stale, headers=auth_headers)
    assert resp_stale.status_code == 201
    id_stale = resp_stale.json()["id"]

    # 2. Create an archived asset
    payload_archived = {"type": "domain", "value": "archived-asset.com", "status": "archived"}
    resp_archived = await client.post("/api/v1/assets", json=payload_archived, headers=auth_headers)
    assert resp_archived.status_code == 201
    id_archived = resp_archived.json()["id"]

    # 3. Re-import stale asset (without status or as default active)
    re_import_stale = {"type": "domain", "value": "stale-asset.com"}
    resp = await client.post("/api/v1/assets", json=re_import_stale, headers=auth_headers)
    assert resp.json()["status"] == "active" # Re-sighting transitions to active

    # 4. Re-import archived asset
    re_import_archived = {"type": "domain", "value": "archived-asset.com"}
    resp = await client.post("/api/v1/assets", json=re_import_archived, headers=auth_headers)
    assert resp.json()["status"] == "archived" # Remains archived

@pytest.mark.asyncio
async def test_first_seen_immutability(client, auth_headers):
    """
    Verify that first_seen cannot be modified via PUT or PATCH requests.
    """
    # Create asset
    payload = {"type": "domain", "value": "immutable.com"}
    resp = await client.post("/api/v1/assets", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    asset = resp.json()
    asset_id = asset["id"]
    original_first_seen = asset["first_seen"]

    # Try to modify first_seen via PUT
    put_payload = {
        "type": "domain",
        "value": "immutable.com",
        "status": "active",
        "source": "manual",
        "tags": [],
        "metadata": {},
        "first_seen": "2000-01-01T00:00:00Z" # Attempted change (should be ignored/read-only)
    }
    # Note: Pydantic schemas AssetUpdate and AssetPatch do not accept first_seen/last_seen,
    # so extra fields passed in request body are ignored or not mapped to database fields.
    resp_put = await client.put(f"/api/v1/assets/{asset_id}", json=put_payload, headers=auth_headers)
    assert resp_put.status_code == 200
    assert resp_put.json()["first_seen"] == original_first_seen

    # Try to modify first_seen via PATCH
    patch_payload = {
        "first_seen": "2000-01-01T00:00:00Z"
    }
    resp_patch = await client.patch(f"/api/v1/assets/{asset_id}", json=patch_payload, headers=auth_headers)
    assert resp_patch.status_code == 200
    assert resp_patch.json()["first_seen"] == original_first_seen
