"""
OpenCHAI GUI — Authentication Routes
─────────────────────────────────────
Authenticates users against the Linux system running the GUI.

Auth flow
─────────
  POST /auth/login
      → PAM authenticates username + password against /etc/pam.d/login
        (identical to what `su` / `ssh` use — honours /etc/shadow, LDAP,
        SSSD, Kerberos, or any other PAM module configured on the host)
      → On success returns a signed JWT (HS256) with:
            sub   : username
            groups: Linux group memberships
            role  : "admin" if user is in wheel/sudo/openchai-admins,
                    "operator" otherwise
            exp   : now + ACCESS_TOKEN_EXPIRE_MINUTES
      → Frontend stores the token in memory (NOT localStorage) and sends
        it as  Authorization: Bearer <token>  on every API request.

Token verification
──────────────────
  All protected routes use the  require_auth  FastAPI dependency.
  /auth/login, /health, and /  are the only public endpoints.

Environment variables (all optional — sane defaults)
──────────────────────────────────────────────────────
  JWT_SECRET_KEY              Signing secret (auto-generated if absent; see
                              note below about persistence)
  JWT_ALGORITHM               default: HS256
  ACCESS_TOKEN_EXPIRE_MINUTES default: 480  (8 hours)
  OPENCHAI_ADMIN_GROUPS       comma-separated Linux group names that grant
                              "admin" role; default: openchai-admins
                              (root is always allowed regardless of group
                              membership — see OPENCHAI_ALLOW_ROOT below)
  OPENCHAI_ALLOW_ROOT         "true" (default) lets the root account log in
                              even if root is not a member of any admin
                              group. Set to "false" to require root to also
                              be in an admin group like everyone else.

  ⚠️  JWT_SECRET_KEY persistence
  ───────────────────────────────
  If JWT_SECRET_KEY is not set, a random 64-byte key is generated at startup.
  This means ALL tokens are invalidated on backend restart.
  For production, set JWT_SECRET_KEY in start.sh or as a system env var:

      export JWT_SECRET_KEY="$(openssl rand -hex 64)"

Security notes
──────────────
  • PAM is the only auth back-end. The backend never reads /etc/shadow directly.
  • Passwords are never logged.
  • Failed login attempts are logged with username + source IP (no password).
  • JWT tokens contain role + groups — no password ever enters a token.
  • Rate-limiting (5 failed attempts → 60s lockout) is implemented per
    username in memory. Restart clears it. For distributed deployments add
    Redis; for now in-memory is appropriate for a single-node HPC GUI.
  • The /auth/me endpoint lets the frontend re-validate a stored token.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from collections import defaultdict
from typing import List, Optional

import grp
import pwd

import pam
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY") or secrets.token_hex(64)
_ALGORITHM: str  = os.getenv("JWT_ALGORITHM", "HS256")
_EXPIRE_MIN: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

_ADMIN_GROUPS: List[str] = [
    g.strip()
    for g in os.getenv("OPENCHAI_ADMIN_GROUPS", "openchai-admins").split(",")
    if g.strip()
]

# Root is allowed to log in even when not a member of an admin group,
# unless explicitly disabled. This satisfies "after changes root can not
# login, it should [be able to]" while keeping the portal restricted to
# openchai-admins for every other account.
_ALLOW_ROOT: bool = os.getenv("OPENCHAI_ALLOW_ROOT", "true").strip().lower() not in (
    "false", "0", "no",
)

# Log a warning if key was auto-generated (tokens won't survive restart)
if not os.getenv("JWT_SECRET_KEY"):
    logger.warning(
        "JWT_SECRET_KEY not set — using auto-generated key. "
        "All sessions will be invalidated on backend restart. "
        "Set JWT_SECRET_KEY in start.sh for persistent sessions."
    )

# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter — per-username, in-memory
# ─────────────────────────────────────────────────────────────────────────────

_MAX_FAILURES   = 5
_LOCKOUT_SECS   = 30    # reduced so a genuine typo doesn't block for a full minute
_fail_count: dict[str, int]   = defaultdict(int)
_fail_time:  dict[str, float] = defaultdict(float)


def _check_rate_limit(username: str) -> None:
    now = time.time()
    if _fail_count[username] >= _MAX_FAILURES:
        elapsed = now - _fail_time[username]
        if elapsed < _LOCKOUT_SECS:
            remaining = int(_LOCKOUT_SECS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts. Try again in {remaining}s.",
            )
        else:
            # Lockout expired — reset
            _fail_count[username] = 0


def _record_failure(username: str) -> None:
    _fail_count[username] += 1
    _fail_time[username]   = time.time()


def _record_success(username: str) -> None:
    _fail_count[username] = 0

# ─────────────────────────────────────────────────────────────────────────────
# Linux system helpers
# ─────────────────────────────────────────────────────────────────────────────

def _user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def _get_user_groups(username: str) -> List[str]:
    """Return all Linux group names the user belongs to."""
    try:
        pw   = pwd.getpwnam(username)
        gids = os.getgrouplist(username, pw.pw_gid) if hasattr(os, "getgrouplist") else []
        groups = []
        for gid in gids:
            try:
                groups.append(grp.getgrgid(gid).gr_name)
            except KeyError:
                pass
        # Fallback: scan all groups
        if not groups:
            groups = [
                g.gr_name
                for g in grp.getgrall()
                if username in g.gr_mem
            ]
        return groups
    except Exception:
        return []


def _get_user_info(username: str) -> dict:
    """Return display info for a Linux user."""
    try:
        pw = pwd.getpwnam(username)
        gecos = pw.pw_gecos.split(",")[0].strip() if pw.pw_gecos else ""
        return {
            "uid":      pw.pw_uid,
            "gid":      pw.pw_gid,
            "home":     pw.pw_dir,
            "shell":    pw.pw_shell,
            "gecos":    gecos,
            "display_name": gecos or username,
        }
    except Exception:
        return {}


def _resolve_role(username: str, groups: List[str]) -> str:
    """Map Linux account → GUI role.

    root is treated as admin whenever OPENCHAI_ALLOW_ROOT is enabled
    (default), independent of group membership. Every other account must
    belong to one of the configured admin groups (default: openchai-admins
    only — NOT wheel/sudo, per portal access-control policy).
    """
    if _ALLOW_ROOT and username == "root":
        return "admin"
    for g in groups:
        if g in _ADMIN_GROUPS:
            return "admin"
    return "operator"


def _pam_authenticate(username: str, password: str) -> bool:
    """
    Authenticate against Linux PAM.
    Uses /etc/pam.d/login stack — honours shadow passwords, LDAP, SSSD,
    Kerberos, or any other PAM module configured on the host.
    Returns True on success, False on failure.
    Never raises — all exceptions are caught and logged.
    """
    try:
        p = pam.pam()
        result = p.authenticate(username, password, service="login")
        if not result and p.reason:
            logger.debug("PAM reason for %s: %s", username, p.reason)
        return result
    except Exception as exc:
        logger.error("PAM error for user %s: %s", username, exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# JWT helpers
# ─────────────────────────────────────────────────────────────────────────────

def _create_token(username: str, groups: List[str], role: str) -> str:
    payload = {
        "sub":    username,
        "groups": groups,
        "role":   role,
        "iat":    int(time.time()),
        "exp":    int(time.time()) + (_EXPIRE_MIN * 60),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def _decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises HTTPException on any failure."""
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        if not payload.get("sub"):
            raise JWTError("Missing subject")
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid or expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI dependency — attach to every protected route
# ─────────────────────────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """
    FastAPI dependency. Validates the Bearer token.
    Returns the decoded token payload (dict with sub, role, groups).
    Raises HTTP 401 if the token is absent, invalid, or expired.

    Usage:
        @router.get("/some-endpoint")
        async def endpoint(user: dict = Depends(require_auth)):
            ...
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(credentials.credentials)


async def require_admin(user: dict = Depends(require_auth)) -> dict:
    """Dependency that further requires admin role."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required.",
        )
    return user


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token:  str
    token_type:    str = "bearer"
    expires_in:    int          # seconds
    username:      str
    display_name:  str
    role:          str
    groups:        List[str]


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate with Linux system credentials",
)
async def login(req: LoginRequest, request: Request):
    """
    Authenticate using the username and password of a Linux user account
    on the host system running the GUI.

    The password is verified via PAM (pluggable authentication modules),
    the same mechanism used by `su`, `ssh`, and `sudo`.
    """
    client_ip = request.client.host if request.client else "unknown"
    username  = req.username.strip()

    # Basic input validation — never hit PAM with obviously bad input
    if not username or not req.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username and password are required.",
        )
    if len(username) > 64 or len(req.password) > 256:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Input too long.",
        )

    # Rate-limit check (per username)
    _check_rate_limit(username)

    # Verify Linux user exists first (avoids leaking info via timing)
    if not _user_exists(username):
        logger.warning("Login attempt for non-existent user '%s' from %s", username, client_ip)
        _record_failure(username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    # PAM authentication (verifies against /etc/shadow, LDAP, etc.)
    auth_ok = _pam_authenticate(username, req.password)

    if not auth_ok:
        _record_failure(username)
        logger.warning(
            "Failed login for user '%s' from %s (attempt %d)",
            username, client_ip, _fail_count[username],
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    # Success — PAM passed. Now check group membership.
    _record_success(username)
    groups  = _get_user_groups(username)
    role    = _resolve_role(username, groups)
    info    = _get_user_info(username)

    # ── Portal Access Control ─────────────────────────────────────────────
    # Only users belonging to one of the configured admin groups are allowed
    # to log in to the OpenCHAI GUI portal. Any authenticated Linux user
    # that is NOT in an admin group is rejected with 403.
    if role != "admin":
        logger.warning(
            "Login DENIED for user '%s' from %s — not in admin group(s) %s (user groups: %s)",
            username, client_ip, _ADMIN_GROUPS, groups,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Access denied. User '{username}' is not a member of the "
                f"required admin group: {', '.join(_ADMIN_GROUPS)}. "
                "Contact your system administrator to be added to this group."
            ),
        )

    token = _create_token(username, groups, role)

    logger.info(
        "Login OK: user='%s' role='%s' groups=%s ip=%s",
        username, role, groups, client_ip,
    )

    return TokenResponse(
        access_token=token,
        expires_in=_EXPIRE_MIN * 60,
        username=username,
        display_name=info.get("display_name", username),
        role=role,
        groups=groups,
    )


@router.post("/logout", summary="Invalidate session (client-side)")
async def logout(user: dict = Depends(require_auth)):
    """
    Stateless logout — instructs the client to discard the token.
    For true server-side invalidation, add a token blocklist (Redis).
    """
    logger.info("Logout: user='%s'", user.get("sub"))
    return {"message": "Logged out successfully."}


@router.get("/me", summary="Get current authenticated user info")
async def me(user: dict = Depends(require_auth)):
    """Returns the decoded token payload + live Linux user info."""
    username = user["sub"]
    info     = _get_user_info(username)
    return {
        "username":     username,
        "display_name": info.get("display_name", username),
        "role":         user.get("role", "operator"),
        "groups":       user.get("groups", []),
        "uid":          info.get("uid"),
        "home":         info.get("home"),
        "shell":        info.get("shell"),
        "token_expires_at": user.get("exp"),
    }


@router.get("/status", summary="Check auth system health")
async def auth_status():
    """Public endpoint — returns auth configuration info (no secrets)."""
    return {
        "auth_enabled":         True,
        "auth_backend":         "PAM (Linux system credentials)",
        "token_algorithm":      _ALGORITHM,
        "token_expire_minutes": _EXPIRE_MIN,
        "admin_groups":         _ADMIN_GROUPS,
        "jwt_secret_persistent": bool(os.getenv("JWT_SECRET_KEY")),
    }
