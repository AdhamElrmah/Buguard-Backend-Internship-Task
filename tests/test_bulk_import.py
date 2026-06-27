import pytest
import asyncio
from datetime import datetime
from unittest.mock import patch

from app.services.asset_service import asset_service


@pytest.mark.asyncio
async def test_bulk_import_partial_success(client, auth_headers):
    """
    Test that bulk import handles valid and invalid items correctly,
    returning success details for valid ones and errors for invalid ones.
    We mock the deduplication/creation of a specific asset to raise an exception.
    """
    payload = {
        "items": [
            {"type": "domain", "value": "valid1.com", "tags": ["bulk"]},
            {
                "type": "domain",
                "value": "fail_me.com",
                "tags": ["bulk"],
            },  # Will fail via mock
            {"type": "ip_address", "value": "8.8.8.8", "tags": ["bulk"]},
        ]
    }

    # Mock _handle_dedup to raise an error for "fail_me.com"
    original_handle_dedup = asset_service._handle_dedup

    async def mock_handle_dedup(session, data):
        if data.value == "fail_me.com":
            raise Exception("Simulated database/runtime constraint error")
        return await original_handle_dedup(session, data)

    with patch.object(asset_service, "_handle_dedup", side_effect=mock_handle_dedup):
        response = await client.post(
            "/api/v1/assets/bulk", json=payload, headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        assert data["total_received"] == 3
        assert data["successful"] == 2
        assert data["failed"] == 1

        # Check errors list
        errors = data["errors"]
        assert len(errors) == 1
        assert errors[0]["index"] == 1
        assert errors[0]["value"] == "fail_me.com"
        assert "Simulated database/runtime constraint error" in errors[0]["error"]

        # Check created assets
        assets = data["assets"]
        assert len(assets) == 2
        assert assets[0]["value"] == "valid1.com"
        assert assets[1]["value"] == "8.8.8.8"


@pytest.mark.asyncio
async def test_bulk_import_deduplication(client, auth_headers):
    """
    Test deduplication logic during import/create:
    - last_seen updated to now
    - tags merged (union)
    - metadata shallow merged
    - status transitions stale -> active
    - first_seen stays unchanged
    """
    # 1. Create initial asset
    initial_payload = {
        "type": "domain",
        "value": "dedup.com",
        "status": "stale",
        "tags": ["initial", "shared"],
        "metadata": {"version": 1, "environment": "prod"},
    }
    resp1 = await client.post(
        "/api/v1/assets", json=initial_payload, headers=auth_headers
    )
    assert resp1.status_code == 201
    asset1 = resp1.json()
    first_seen_1 = asset1["first_seen"]
    last_seen_1 = asset1["last_seen"]

    # Sleep slightly to ensure timestamps would differ
    await asyncio.sleep(0.1)

    # 2. Re-import/Create the same asset with new metadata/tags
    second_payload = {
        "type": "domain",
        "value": "dedup.com",
        "tags": ["shared", "new-tag"],
        "metadata": {"version": 2, "scanner": "shodan"},
    }
    resp2 = await client.post(
        "/api/v1/assets", json=second_payload, headers=auth_headers
    )
    assert resp2.status_code == 201
    asset2 = resp2.json()

    # 3. Assertions
    # Status transitioned stale -> active
    assert asset2["status"] == "active"

    # tags merged (union of ['initial', 'shared'] and ['shared', 'new-tag'])
    assert set(asset2["tags"]) == {"initial", "shared", "new-tag"}

    # metadata shallow merged
    assert asset2["metadata"] == {
        "version": 2,  # Overwritten by new value
        "environment": "prod",  # Preserved from old value
        "scanner": "shodan",  # Added from new value
    }

    # first_seen is immutable and remains unchanged
    assert asset2["first_seen"] == first_seen_1

    # last_seen is updated (is strictly greater than old last_seen)
    t1 = datetime.fromisoformat(last_seen_1.replace("Z", "+00:00"))
    t2 = datetime.fromisoformat(asset2["last_seen"].replace("Z", "+00:00"))
    assert t2 > t1
