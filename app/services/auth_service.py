from typing import Any, Dict, List
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.user import crud_user
from app.crud.organization import crud_organization
from app.crud.property import crud_property
from app.crud.role import crud_role
from app.crud.organization_user import crud_organization_user
from app.crud.property_user import crud_property_user
from app.crud.property_booking_settings import crud_property_booking_settings
from app.models.role import Role
from app.models.organization_user import OrganizationUser
from app.models.property_user import PropertyUser
from app.schemas.auth import (
    SignupRequest,
    SignupResponse,
    LoginRequest,
    TokenResponse,
    AuthMeResponse,
)
from app.schemas.organization import OrganizationResponse
from app.schemas.property import PropertyResponse
from app.schemas.property_booking_settings import PropertyBookingSettingsCreate
from app.schemas.user import UserResponse
from app.utils.enums import OrganizationStatus, EntityStatus, RoleScope, UserMembershipStatus
from app.utils.exceptions import (
    AuthenticationException,
    DuplicateEntityException,
    EntityNotFoundException,
    ValidationException,
)
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.utils.validators import slugify


class AuthService:
    async def signup_flow(self, db: AsyncSession, signup_in: SignupRequest) -> SignupResponse:
        """
        Executes the atomic multi-step onboarding signup flow:
          1. Create user account
          2. Set up organization
          3. Provision first property + default booking settings
          4. Assign organization owner & property manager roles
          5. Generate access & refresh tokens
        """
        # 1. Validate User Email Uniqueness
        existing_user = await crud_user.get_by_email(db, signup_in.account.email)
        if existing_user:
            raise DuplicateEntityException("User", "email", signup_in.account.email)

        # 2. Determine Organization Slug
        org_slug = signup_in.organization.slug
        if not org_slug:
            org_slug = slugify(signup_in.organization.name)
        if not org_slug:
            org_slug = f"org-{uuid.uuid4().hex[:8]}"

        # 3. Determine Property Code
        prop_code = signup_in.property.code
        if not prop_code:
            cleaned_name = slugify(signup_in.property.name).upper().replace("-", "")
            prop_code = f"{cleaned_name[:4]}-01" if cleaned_name else f"PROP-{uuid.uuid4().hex[:4].upper()}"
        prop_code = prop_code.strip().upper()

        # 4. Create User Account
        user = await crud_user.create_user(
            db,
            email=signup_in.account.email,
            password=signup_in.account.password,
            full_name=signup_in.account.full_name,
            phone=signup_in.account.phone,
            is_superuser=False,
        )

        # 5. Create Organization
        org_data = {
            "name": signup_in.organization.name.strip(),
            "slug": org_slug,
            "status": OrganizationStatus.ACTIVE.value,
        }
        org = await crud_organization.create(db, obj_in=org_data)

        # 6. Seed Default System Roles for Organization
        owner_role = await crud_role.create(
            db,
            obj_in={
                "name": "Owner",
                "scope": RoleScope.ORGANIZATION.value,
                "organization_id": org.id,
                "is_system": True,
            },
        )
        prop_manager_role = await crud_role.create(
            db,
            obj_in={
                "name": "Property Manager",
                "scope": RoleScope.PROPERTY.value,
                "organization_id": org.id,
                "is_system": True,
            },
        )

        # 7. Assign User as Organization Owner
        await crud_organization_user.create(
            db,
            obj_in={
                "organization_id": org.id,
                "user_id": user.id,
                "role_id": owner_role.id,
                "status": UserMembershipStatus.ACTIVE.value,
            },
        )

        # 8. Create First Property
        prop_data = {
            "organization_id": org.id,
            "name": signup_in.property.name.strip(),
            "code": prop_code,
            "address_line_1": signup_in.property.address_line_1,
            "address_line_2": signup_in.property.address_line_2,
            "city": signup_in.property.city,
            "state": signup_in.property.state,
            "country": signup_in.property.country,
            "postal_code": signup_in.property.postal_code,
            "timezone": signup_in.property.timezone,
            "currency": signup_in.property.currency,
            "status": EntityStatus.ACTIVE.value,
        }
        prop = await crud_property.create(db, obj_in=prop_data)

        # 9. Initialize Default Booking Settings for Property
        default_booking_settings = PropertyBookingSettingsCreate(property_id=prop.id)
        settings_dict = default_booking_settings.model_dump(exclude_unset=True)
        settings_dict["property_id"] = prop.id
        await crud_property_booking_settings.create(db, obj_in=settings_dict)

        # Commit all entities atomically
        await db.commit()
        await db.refresh(user)
        await db.refresh(org)
        await db.refresh(prop)

        # 11. Generate JWT Access and Refresh Tokens
        token_claims = {
            "sub": user.id,
            "email": user.email,
            "role": "authenticated",
            "org_id": org.id,
            "prop_id": prop.id,
        }
        access_token = create_access_token(token_claims)
        refresh_token = create_refresh_token({"sub": user.id})

        return SignupResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(org),
            property=PropertyResponse.model_validate(prop),
            message="Sign up and initial onboarding completed successfully. Welcome to CloudKey!",
        )

    async def authenticate_user(self, db: AsyncSession, login_in: LoginRequest) -> TokenResponse:
        """Authenticate user by email and password, returning tokens."""
        user = await crud_user.get_by_email(db, login_in.email)
        if not user or not verify_password(login_in.password, user.hashed_password):
            raise AuthenticationException("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationException("User account is inactive. Please contact support.")

        token_claims = {
            "sub": user.id,
            "email": user.email,
            "role": "authenticated",
        }
        access_token = create_access_token(token_claims)
        refresh_token = create_refresh_token({"sub": user.id})

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )

    async def get_user_profile(self, db: AsyncSession, user_id: str) -> AuthMeResponse:
        """Get profile details and all organizations/properties for the user."""
        user = await crud_user.get(db, user_id)
        if not user:
            raise EntityNotFoundException("User", user_id)

        # Query organization memberships
        org_users_res = await db.execute(
            select(OrganizationUser).where(OrganizationUser.user_id == user_id)
        )
        org_users = org_users_res.scalars().all()
        org_list: List[Dict[str, Any]] = []
        user_orgs = []
        for ou in org_users:
            org = await crud_organization.get(db, ou.organization_id)
            if org:
                role = await crud_role.get(db, ou.role_id)
                user_orgs.append((org, role, ou.status))
                org_list.append({
                    "id": org.id,
                    "name": org.name,
                    "slug": org.slug,
                    "role": role.name if role else None,
                    "status": ou.status,
                })

        # Query direct property memberships
        prop_users_res = await db.execute(
            select(PropertyUser).where(PropertyUser.user_id == user_id)
        )
        prop_users = prop_users_res.scalars().all()
        prop_list: List[Dict[str, Any]] = []
        seen_prop_ids = set()

        for pu in prop_users:
            prop = await crud_property.get(db, pu.property_id)
            if prop:
                role = await crud_role.get(db, pu.role_id)
                seen_prop_ids.add(prop.id)
                prop_list.append({
                    "id": prop.id,
                    "organization_id": prop.organization_id,
                    "name": prop.name,
                    "code": prop.code,
                    "role": role.name if role else None,
                    "status": pu.status,
                    "is_setup_completed": prop.is_setup_completed,
                    "setup_step": prop.setup_step,
                    "timezone": prop.timezone,
                    "currency": prop.currency,
                })

        # For organization-level users (e.g. Owner), automatically grant visibility to all properties in their org
        for org, role, status in user_orgs:
            if role and role.scope == RoleScope.ORGANIZATION.value:
                org_props = await crud_property.get_by_organization(db, organization_id=org.id)
                for prop in org_props:
                    if prop.id not in seen_prop_ids:
                        seen_prop_ids.add(prop.id)
                        prop_list.append({
                            "id": prop.id,
                            "organization_id": prop.organization_id,
                            "name": prop.name,
                            "code": prop.code,
                            "role": role.name,
                            "status": status,
                            "is_setup_completed": prop.is_setup_completed,
                            "setup_step": prop.setup_step,
                            "timezone": prop.timezone,
                            "currency": prop.currency,
                        })

        return AuthMeResponse(
            user=UserResponse.model_validate(user),
            organizations=org_list,
            properties=prop_list,
        )


auth_service = AuthService()
