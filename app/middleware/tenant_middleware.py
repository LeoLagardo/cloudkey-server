import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.time()

        # Set request/correlation ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        # Extract tenant / organization ID header if present
        organization_id = request.headers.get("X-Organization-ID")
        request.state.organization_id = organization_id

        response = await call_next(request)

        # Append timing & tracing headers
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        response.headers["X-Request-ID"] = request_id
        if organization_id:
            response.headers["X-Organization-ID"] = organization_id

        return response
