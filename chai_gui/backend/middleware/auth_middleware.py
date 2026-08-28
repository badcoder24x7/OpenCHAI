"""
OpenCHAI GUI — Auth Middleware
──────────────────────────────
Injects JWT verification as a FastAPI middleware so every route is
automatically protected without needing Depends(require_auth) on each one.

PUBLIC_PATHS — endpoints that do NOT require a token:
  /               root redirect
  /health         system health
  /docs           Swagger UI
  /openapi.json   OpenAPI schema
  /redoc          ReDoc UI
  /auth/login     login endpoint
  /auth/status    auth config info
"""

from __future__ import annotations

import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

PUBLIC_PATHS: frozenset[str] = frozenset({
    "/",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/login",
    "/auth/status",
})

PUBLIC_PREFIXES: tuple[str, ...] = (
    "/docs/",
    "/redoc/",
    "/static/",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Validates Bearer token on every non-public request.
    Attaches decoded payload to request.state.user.

    The signing secret and algorithm are imported directly from routes.auth
    (the single source of truth that creates tokens) rather than re-reading
    JWT_SECRET_KEY from the environment here. This guarantees the value used
    to verify a token is always identical to the value used to sign it,
    even if this module is imported/executed at a different env-var
    snapshot than auth.py (e.g. when the app is started by a process
    manager that doesn't go through start.sh's export step).
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[len("Bearer "):]

        # Import lazily to avoid a circular import at module load time
        # (routes.auth imports nothing from middleware, so this is safe).
        from routes.auth import _SECRET_KEY, _ALGORITHM

        try:
            payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
            request.state.user = payload
        except JWTError as exc:
            logger.debug("Token rejected [%s]: %s", path, exc)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Token invalid or expired. Please log in again."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
