from typing import Any, Optional
from fastapi import HTTPException, status


class PMSException(HTTPException):
    def __init__(
        self,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: str = "Internal server error occurred.",
        headers: Optional[dict[str, Any]] = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class EntityNotFoundException(PMSException):
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} with identifier '{entity_id}' not found.",
        )


class TenantMismatchException(PMSException):
    def __init__(self, detail: str = "Resource does not belong to the requested organization/tenant."):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class DuplicateEntityException(PMSException):
    def __init__(self, entity_name: str, field_name: str, value: Any):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{entity_name} with {field_name}='{value}' already exists.",
        )


class ValidationException(PMSException):
    def __init__(self, detail: str = "Validation failed for the requested operation."):
        super().__init__(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail=detail,
        )


class AuthenticationException(PMSException):
    def __init__(self, detail: str = "Invalid credentials or unauthorized access."):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
