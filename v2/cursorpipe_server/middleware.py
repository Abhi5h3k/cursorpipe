"""Request ID generation and structured request/response logging middleware."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("cursorpipe.access")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assigns a unique request ID to every request and logs access lines.

    - If the client sends X-Request-ID it is echoed back unchanged.
    - If absent, a new UUID4 is generated.
    - Logs one line on arrival and one on completion with status + duration.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        start = time.perf_counter()

        logger.info(
            "[REQUEST]  %s %s  request_id=%s",
            request.method,
            request.url.path,
            request_id,
        )

        response: Response = await call_next(request)

        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers[REQUEST_ID_HEADER] = request_id

        logger.info(
            "[RESPONSE] %s %s  request_id=%s  status=%d  duration_ms=%d",
            request.method,
            request.url.path,
            request_id,
            response.status_code,
            duration_ms,
        )

        return response
