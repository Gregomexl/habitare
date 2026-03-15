"""Pure ASGI middleware: inject X-Request-ID into every response.

Uses pure ASGI (not BaseHTTPMiddleware) to avoid streaming response
and exception handler interaction issues in Starlette.

Context7 confirmed patterns:
- Request(scope) to access request.state
- MutableHeaders(scope=message) to inject response headers
- scope["type"] check to pass through non-HTTP (WebSocket, lifespan)
"""
import uuid
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Store on request.state so exception handlers can read it
        request.state.request_id = request_id

        async def send_with_request_id(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", request_id)
            await send(message)

        await self.app(scope, receive, send_with_request_id)
