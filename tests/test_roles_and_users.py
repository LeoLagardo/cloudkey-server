import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_roles_and_permissions(async_client: AsyncClient):
    # 1. Create Permission
    perm_res = await async_client.post(
        "/api/v1/roles/permissions",
        json={
            "code": "rooms:manage",
            "name": "Manage Rooms",
            "module": "ROOMS",
            "description": "Create and edit physical rooms",
        },
    )
    assert perm_res.status_code == 201
    perm_id = perm_res.json()["id"]

    # 2. List Permissions
    list_perm_res = await async_client.get("/api/v1/roles/permissions")
    assert list_perm_res.status_code == 200
    assert len(list_perm_res.json()) >= 1

    # 3. Create Role with permission
    role_res = await async_client.post(
        "/api/v1/roles",
        json={
            "name": "Front Desk Manager",
            "scope": "PROPERTY",
            "is_system": False,
            "permission_ids": [perm_id],
        },
    )
    assert role_res.status_code == 201
    role_data = role_res.json()
    assert role_data["name"] == "Front Desk Manager"
    assert len(role_data["permissions"]) == 1
    assert role_data["permissions"][0]["id"] == perm_id
    role_id = role_data["id"]

    # 4. Get Role by ID
    get_role_res = await async_client.get(f"/api/v1/roles/{role_id}")
    assert get_role_res.status_code == 200
    assert get_role_res.json()["id"] == role_id


@pytest.mark.asyncio
async def test_organization_and_property_users(async_client: AsyncClient):
    # Setup Org, Property & Role
    org_res = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Access Group", "slug": "access-group"},
    )
    org_id = org_res.json()["id"]

    prop_res = await async_client.post(
        "/api/v1/properties",
        json={"name": "Access Inn", "code": "ACC-01"},
        headers={"X-Organization-ID": org_id},
    )
    prop_id = prop_res.json()["id"]

    role_res = await async_client.post(
        "/api/v1/roles",
        json={
            "name": "General Staff",
            "scope": "ORGANIZATION",
            "organization_id": org_id,
        },
    )
    role_id = role_res.json()["id"]

    # 1. Assign Organization User
    org_user_payload = {
        "user_id": "supabase-user-uuid-1",
        "role_id": role_id,
        "status": "ACTIVE",
    }
    assign_org_res = await async_client.post(
        f"/api/v1/organization-users/{org_id}",
        json=org_user_payload,
    )
    assert assign_org_res.status_code == 201
    org_user_id = assign_org_res.json()["id"]

    # 2. List Organization Users
    list_org_users = await async_client.get(f"/api/v1/organization-users/{org_id}")
    assert list_org_users.status_code == 200
    assert len(list_org_users.json()) == 1

    # 3. Duplicate Org User should fail
    dup_org_res = await async_client.post(
        f"/api/v1/organization-users/{org_id}",
        json=org_user_payload,
    )
    assert dup_org_res.status_code == 409

    # 4. Assign Property User
    prop_user_payload = {
        "user_id": "supabase-user-uuid-2",
        "role_id": role_id,
        "status": "ACTIVE",
    }
    assign_prop_res = await async_client.post(
        f"/api/v1/property-users/{prop_id}",
        json=prop_user_payload,
    )
    assert assign_prop_res.status_code == 201
    prop_user_id = assign_prop_res.json()["id"]

    # 5. List Property Users
    list_prop_users = await async_client.get(f"/api/v1/property-users/{prop_id}")
    assert list_prop_users.status_code == 200
    assert len(list_prop_users.json()) == 1
