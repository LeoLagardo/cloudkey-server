from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthenticatedUser
from app.schemas.auth import (
    SignupRequest,
    SignupResponse,
    LoginRequest,
    TokenResponse,
    AuthMeResponse,
)
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User Registration and PMS Onboarding Flow",
    description="Atomic signup: creates user account, configures organization, sets up initial property with booking settings, assigns roles, and issues JWT tokens.",
)
async def signup(
    signup_in: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> SignupResponse:
    return await auth_service.signup_flow(db, signup_in=signup_in)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User Authentication Login",
    description="Authenticate with email and password to receive JWT access and refresh tokens.",
)
async def login(
    login_in: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    return await auth_service.authenticate_user(db, login_in=login_in)


@router.get(
    "/me",
    response_model=AuthMeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current User Profile & Memberships",
    description="Returns user details along with their organizations and property roles.",
)
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthMeResponse:
    return await auth_service.get_user_profile(db, user_id=current_user.id)
