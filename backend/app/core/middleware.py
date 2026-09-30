"""Security middleware (Phase 8): headers, HTTPS redirect, request size limit."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
# /docs loads Swagger UI assets from a CDN, so it gets a looser CSP.
API_CSP = "default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, hsts: bool = False):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
            response.headers.setdefault("Content-Security-Policy", API_CSP)
        response.headers.setdefault("Cache-Control", "no-store")
        if self.hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect plain HTTP to HTTPS, honouring X-Forwarded-Proto from the TLS proxy."""

    async def dispatch(self, request: Request, call_next):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto == "http" and request.url.path != "/health":
            return RedirectResponse(str(request.url.replace(scheme="https")), status_code=307)
        return await call_next(request)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized bodies on selected path prefixes using Content-Length."""

    def __init__(self, app, limits: dict[str, int]):
        super().__init__(app)
        self.limits = limits

    async def dispatch(self, request: Request, call_next):
        for prefix, limit in self.limits.items():
            if request.url.path.startswith(prefix):
                length = request.headers.get("content-length")
                if length is None and request.method in ("POST", "PUT", "PATCH"):
                    return JSONResponse({"detail": "Content-Length required"}, status_code=411)
                if length is not None and int(length) > limit:
                    return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return await call_next(request)
