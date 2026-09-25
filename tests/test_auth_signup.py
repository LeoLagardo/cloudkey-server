import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup_flow_nested_payload(async_client: AsyncClient):
    signup_payload = {
        "account": {
            "email": "hotelier@cloudkey.com",
            "password": "SecurePassword123!",
            "full_name": "Alexander Wright",
            "phone": "+919876543210",
        },
        "organization": {
            "name": "Wright Hospitality Group",
            "slug": "wright-hospitality",
        },
        "property": {
            "name": "Wright Grand Suites",
            "code": "WGS-01",
            "city": "Bengaluru",
            "state": "Karnataka",
            "country": "India",
            "postal_code": "560001",
            "timezone": "Asia/Kolkata",
            "currency": "INR",
        },
    }

    # 1. Execute signup flow
    response = await async_client.post("/api/v1/auth/signup", json=signup_payload)
    assert response.status_code == 201, response.text
    data = response.json()

    # 2. Verify response structure
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert "Welcome to CloudKey" in data["message"]

    # 3. Verify user details
    user = data["user"]
    assert user["email"] == "hotelier@cloudkey.com"
    assert user["full_name"] == "Alexander Wright"
    assert user["is_active"] is True
    assert "id" in user

    # 4. Verify organization details
    org = data["organization"]
    assert org["name"] == "Wright Hospitality Group"
    assert org["slug"] == "wright-hospitality"
    assert org["status"] == "ACTIVE"

    # 5. Verify property details
    prop = data["property"]
    assert prop["name"] == "Wright Grand Suites"
    assert prop["code"] == "WGS-01"
    assert prop["organization_id"] == org["id"]
    assert prop["currency"] == "INR"

    # 6. Verify default booking settings were automatically created for the property
    settings_res = await async_client.get(
        f"/api/v1/booking-settings/{prop['id']}",
        headers={"X-Organization-ID": org["id"]},
    )
    assert settings_res.status_code == 200
    booking_settings = settings_res.json()
    assert booking_settings["property_id"] == prop["id"]
    assert booking_settings["nightly_booking_enabled"] is True

    # 7. Verify organization users & property users memberships
    org_users_res = await async_client.get(f"/api/v1/organization-users/{org['id']}")
    assert org_users_res.status_code == 200
    org_users = org_users_res.json()
    assert len(org_users) == 1
    assert org_users[0]["user_id"] == user["id"]
    assert org_users[0]["status"] == "ACTIVE"

    # Only organization user is created for owner - NOT a property user
    prop_users_res = await async_client.get(f"/api/v1/property-users/{prop['id']}")
    assert prop_users_res.status_code == 200
    prop_users = prop_users_res.json()
    assert len(prop_users) == 0


@pytest.mark.asyncio
async def test_signup_flow_flat_payload_and_auto_slug(async_client: AsyncClient):
    # Flat payload with auto-slug and auto property code
    flat_payload = {
        "email": "sarah.connor@skylineresorts.com",
        "password": "Password456!",
        "full_name": "Sarah Connor",
        "organization_name": "Skyline Resorts International",
        "property_name": "Skyline Highland Resort",
        "city": "Manali",
    }

    response = await async_client.post("/api/v1/auth/signup", json=flat_payload)
    assert response.status_code == 201, response.text
    data = response.json()

    # Verify auto-generated slug
    org = data["organization"]
    assert org["slug"] == "skyline-resorts-international"

    # Verify auto-generated code
    prop = data["property"]
    assert prop["code"].startswith("SKYL") or prop["code"].startswith("PROP")


@pytest.mark.asyncio
async def test_signup_duplicate_email_and_slug(async_client: AsyncClient):
    payload = {
        "account": {
            "email": "duplicate@test.com",
            "password": "Password123!",
            "full_name": "First User",
        },
        "organization": {
            "name": "Original Org",
            "slug": "original-slug",
        },
        "property": {
            "name": "Original Hotel",
            "code": "ORIG-01",
        },
    }

    # 1. First signup succeeds
    res1 = await async_client.post("/api/v1/auth/signup", json=payload)
    assert res1.status_code == 201

    # 2. Duplicate email fails with 409
    dup_email_payload = {
        "account": {
            "email": "duplicate@test.com",
            "password": "AnotherPassword!",
            "full_name": "Second User",
        },
        "organization": {
            "name": "Different Org",
            "slug": "different-slug",
        },
        "property": {
            "name": "Different Hotel",
        },
    }
    res2 = await async_client.post("/api/v1/auth/signup", json=dup_email_payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]

    # 3. Duplicate organization slug fails with 409
    dup_slug_payload = {
        "account": {
            "email": "unique@test.com",
            "password": "Password123!",
            "full_name": "Third User",
        },
        "organization": {
            "name": "Another Org",
            "slug": "original-slug",
        },
        "property": {
            "name": "Third Hotel",
        },
    }
    res3 = await async_client.post("/api/v1/auth/signup", json=dup_slug_payload)
    assert res3.status_code == 409
    assert "already exists" in res3.json()["detail"]


@pytest.mark.asyncio
async def test_login_and_auth_me(async_client: AsyncClient):
    # 1. Sign up
    signup_payload = {
        "account": {
            "email": "login_user@cloudkey.com",
            "password": "MySecretPassword123",
            "full_name": "Login Test User",
        },
        "organization": {
            "name": "Login Testing Org",
            "slug": "login-test-org",
        },
        "property": {
            "name": "Login Test Lodge",
            "code": "LTL-01",
        },
    }
    signup_res = await async_client.post("/api/v1/auth/signup", json=signup_payload)
    assert signup_res.status_code == 201
    signup_token = signup_res.json()["access_token"]

    # 2. Test successful login
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "login_user@cloudkey.com", "password": "MySecretPassword123"},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    access_token = login_data["access_token"]
    assert login_data["user"]["email"] == "login_user@cloudkey.com"

    # 3. Test wrong password
    bad_login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "login_user@cloudkey.com", "password": "WrongPassword"},
    )
    assert bad_login_res.status_code == 401

    # 4. Test GET /api/v1/auth/me with valid Bearer token
    me_res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user"]["email"] == "login_user@cloudkey.com"
    assert len(me_data["organizations"]) == 1
    assert me_data["organizations"][0]["slug"] == "login-test-org"
    assert me_data["organizations"][0]["role"] == "Owner"
    assert len(me_data["properties"]) == 1
    assert me_data["properties"][0]["code"] == "LTL-01"
    assert me_data["properties"][0]["role"] == "Owner"

    # 5. Test GET /api/v1/auth/me with invalid token
    invalid_token_res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert invalid_token_res.status_code == 401
