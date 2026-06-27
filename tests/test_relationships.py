import pytest
from uuid import uuid4


@pytest.mark.asyncio
async def test_relationship_creation_and_rejection(client, auth_headers):
    """
    Test creating a relationship, rejecting duplicates (409),
    and rejecting non-existent assets (404).
    """
    # 1. Create two assets
    asset_a_payload = {"type": "domain", "value": "source.com"}
    asset_b_payload = {"type": "subdomain", "value": "sub.source.com"}

    resp_a = await client.post(
        "/api/v1/assets", json=asset_a_payload, headers=auth_headers
    )
    resp_b = await client.post(
        "/api/v1/assets", json=asset_b_payload, headers=auth_headers
    )
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201

    id_a = resp_a.json()["id"]
    id_b = resp_b.json()["id"]

    # 2. Create relationship between A and B
    rel_payload = {
        "source_asset_id": id_a,
        "target_asset_id": id_b,
        "relationship_type": "belongs_to",
    }
    response = await client.post(
        "/api/v1/relationships", json=rel_payload, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["source_asset_id"] == id_a
    assert data["target_asset_id"] == id_b
    assert data["relationship_type"] == "belongs_to"
    data["id"]

    # 3. Reject duplicate relationship (409 Conflict)
    response = await client.post(
        "/api/v1/relationships", json=rel_payload, headers=auth_headers
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "conflict"

    # 4. Reject relationships with non-existent assets (404 Not Found)
    fake_id = str(uuid4())
    bad_payload_source = {
        "source_asset_id": fake_id,
        "target_asset_id": id_b,
        "relationship_type": "belongs_to",
    }
    bad_payload_target = {
        "source_asset_id": id_a,
        "target_asset_id": fake_id,
        "relationship_type": "belongs_to",
    }

    response = await client.post(
        "/api/v1/relationships", json=bad_payload_source, headers=auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "not_found"

    response = await client.post(
        "/api/v1/relationships", json=bad_payload_target, headers=auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "not_found"


@pytest.mark.asyncio
async def test_relationship_retrieval_and_deletion(client, auth_headers):
    """
    Test retrieving asset relationships and deleting them.
    """
    # Create two assets and link them
    resp_a = await client.post(
        "/api/v1/assets",
        json={"type": "domain", "value": "a.com"},
        headers=auth_headers,
    )
    resp_b = await client.post(
        "/api/v1/assets",
        json={"type": "ip_address", "value": "1.1.1.1"},
        headers=auth_headers,
    )
    id_a = resp_a.json()["id"]
    id_b = resp_b.json()["id"]

    rel_payload = {
        "source_asset_id": id_a,
        "target_asset_id": id_b,
        "relationship_type": "resolves_to",
    }
    resp_rel = await client.post(
        "/api/v1/relationships", json=rel_payload, headers=auth_headers
    )
    assert resp_rel.status_code == 201
    rel_id = resp_rel.json()["id"]

    # Retrieve relationships of Asset A (should return 1 relationship)
    response = await client.get(f"/api/v1/assets/{id_a}/relationships")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == rel_id

    # Retrieve relationships of non-existent asset (404)
    response = await client.get(f"/api/v1/assets/{uuid4()}/relationships")
    assert response.status_code == 404

    # Delete the relationship
    response = await client.delete(
        f"/api/v1/relationships/{rel_id}", headers=auth_headers
    )
    assert response.status_code == 204

    # Verify relationship list is now empty
    response = await client.get(f"/api/v1/assets/{id_a}/relationships")
    assert response.status_code == 200
    assert len(response.json()) == 0


@pytest.mark.asyncio
async def test_relationship_cascade_delete(client, auth_headers):
    """
    Verify cascade delete: when an asset is deleted, all its relationships are removed.
    """
    # Create three assets: A -> B -> C
    resp_a = await client.post(
        "/api/v1/assets",
        json={"type": "domain", "value": "a.com"},
        headers=auth_headers,
    )
    resp_b = await client.post(
        "/api/v1/assets",
        json={"type": "subdomain", "value": "b.a.com"},
        headers=auth_headers,
    )
    resp_c = await client.post(
        "/api/v1/assets",
        json={"type": "ip_address", "value": "1.1.1.1"},
        headers=auth_headers,
    )
    id_a = resp_a.json()["id"]
    id_b = resp_b.json()["id"]
    id_c = resp_c.json()["id"]

    # Link A -> B and B -> C
    await client.post(
        "/api/v1/relationships",
        json={
            "source_asset_id": id_a,
            "target_asset_id": id_b,
            "relationship_type": "belongs_to",
        },
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/relationships",
        json={
            "source_asset_id": id_b,
            "target_asset_id": id_c,
            "relationship_type": "resolves_to",
        },
        headers=auth_headers,
    )

    # Verify A has 1 relationship (A -> B)
    resp = await client.get(f"/api/v1/assets/{id_a}/relationships")
    assert len(resp.json()) == 1

    # Verify B has 2 relationships (A -> B and B -> C)
    resp = await client.get(f"/api/v1/assets/{id_b}/relationships")
    assert len(resp.json()) == 2

    # Delete Asset B
    delete_resp = await client.delete(f"/api/v1/assets/{id_b}", headers=auth_headers)
    assert delete_resp.status_code == 204

    # Verify A's relationship list is now empty (because A -> B cascade deleted)
    resp = await client.get(f"/api/v1/assets/{id_a}/relationships")
    assert len(resp.json()) == 0

    # Verify C's relationship list is now empty (because B -> C cascade deleted)
    resp = await client.get(f"/api/v1/assets/{id_c}/relationships")
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_asset_graph_retrieval(client, auth_headers):
    """
    Verify that GET /api/v1/assets/{id}/graph returns the asset
    along with its related assets and relationship directions.
    """
    # Create source, middle, and target assets: A -> B -> C
    resp_a = await client.post(
        "/api/v1/assets",
        json={"type": "domain", "value": "a.com"},
        headers=auth_headers,
    )
    resp_b = await client.post(
        "/api/v1/assets",
        json={"type": "subdomain", "value": "b.a.com"},
        headers=auth_headers,
    )
    resp_c = await client.post(
        "/api/v1/assets",
        json={"type": "ip_address", "value": "1.1.1.1"},
        headers=auth_headers,
    )
    id_a = resp_a.json()["id"]
    id_b = resp_b.json()["id"]
    id_c = resp_c.json()["id"]

    # Link A -> B and B -> C
    await client.post(
        "/api/v1/relationships",
        json={
            "source_asset_id": id_a,
            "target_asset_id": id_b,
            "relationship_type": "belongs_to",
        },
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/relationships",
        json={
            "source_asset_id": id_b,
            "target_asset_id": id_c,
            "relationship_type": "resolves_to",
        },
        headers=auth_headers,
    )

    # Get graph for Middle Asset B
    response = await client.get(f"/api/v1/assets/{id_b}/graph")
    assert response.status_code == 200
    data = response.json()

    # Asset under query should be B
    assert data["asset"]["id"] == id_b
    assert data["asset"]["value"] == "b.a.com"

    # Relationships list should contain both connections (incoming A->B and outgoing B->C)
    relationships = data["relationships"]
    assert len(relationships) == 2

    # Verify connection from A (incoming to B)
    incoming = next(r for r in relationships if r["direction"] == "incoming")
    assert incoming["relationship_type"] == "belongs_to"
    assert incoming["asset"]["id"] == id_a
    assert incoming["asset"]["value"] == "a.com"

    # Verify connection to C (outgoing from B)
    outgoing = next(r for r in relationships if r["direction"] == "outgoing")
    assert outgoing["relationship_type"] == "resolves_to"
    assert outgoing["asset"]["id"] == id_c
    assert outgoing["asset"]["value"] == "1.1.1.1"

    # Verify 404 for non-existent asset graph
    response = await client.get(f"/api/v1/assets/{uuid4()}/graph")
    assert response.status_code == 404
