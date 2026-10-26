from typing import Any, Optional


class AiosellError(Exception):
    """Base exception for all Aiosell channel manager operations."""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.details = details


class AiosellConfigError(AiosellError):
    """Raised when configuration or partner settings are missing or invalid."""
    pass


class AiosellAuthError(AiosellError):
    """Raised when authentication credentials fail or are invalid."""
    pass


class AiosellMappingError(AiosellError):
    """Raised when property, room type, or rate plan mapping fails."""
    pass


class AiosellApiError(AiosellError):
    """Raised when Aiosell API returns an error or non-2xx status code."""
    def __init__(self, message: str, status_code: int, response_body: Optional[Any] = None):
        super().__init__(f"[{status_code}] {message}", details=response_body)
        self.status_code = status_code
        self.response_body = response_body


class AiosellDecryptionError(AiosellError):
    """Raised when decrypting sensitive credit card payload fails."""
    pass


class AiosellWebhookError(AiosellError):
    """Raised when processing inbound webhook event fails."""
    pass
