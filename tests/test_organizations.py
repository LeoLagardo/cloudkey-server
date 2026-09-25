import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_organization(async_client: AsyncClient):
    # 1. Create Organization
    payload = {
        "name": "Luxury Hotel Group",
        "slug": "luxury-hotel-group",
        "status": "ACTIVE",
    }
    response = await async_client.post("/api/v1/organizations", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["slug"] == payload["slug"]
    assert data["status"] == "ACTIVE"
    org_id = data["id"]

    # 2. Get Organization by ID
    get_res = await async_client.get(f"/api/v1/organizations/{org_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == org_id

    # 3. List Organizations
    list_res = await async_client.get("/api/v1/organizations")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1


@pytest.mark.asyncio
async def test_duplicate_organization_slug(async_client: AsyncClient):
    payload = {"name": "Org 1", "slug": "test-duplicate"}
    res1 = await async_client.post("/api/v1/organizations", json=payload)
    assert res1.status_code == 201

    # Attempt to create duplicate slug
    res2 = await async_client.post("/api/v1/organizations", json=payload)
    assert res2.status_code == 409
