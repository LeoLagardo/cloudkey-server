from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
import jwt

from app.config import settings

security = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    id: str
    email: Optional[str] = None
    role: str = "authenticated"
    is_superuser: bool = False
    metadata: dict = {}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthenticatedUser:
    """
    Validates Supabase / Bearer JWT token if provided.
    If no token is supplied in development mode, returns a mock development user.
    """
    if not credentials:
        # In development/test mode, provide a mock user to allow seamless rapid development
        if settings.ENVIRONMENT in ["development", "testing"]:
            return AuthenticatedUser(
                id="dev-user-00000000-0000-0000-0000-000000000000",
                email="dev@cloudkey.local",
                role="authenticated",
                is_superuser=True,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Decode and verify with application SECRET_KEY (or fallback to SUPABASE_JWT_SECRET)
    jwt_secret = settings.SECRET_KEY or settings.SUPABASE_JWT_SECRET
    try:
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return AuthenticatedUser(
            id=str(payload.get("sub", "")),
            email=payload.get("email"),
            role=payload.get("role", "authenticated"),
            is_superuser=bool(payload.get("is_superuser", payload.get("role") == "service_role")),
            metadata=payload.get("user_metadata", {}),
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
