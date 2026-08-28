"""Session-based authentication for the NiceGUI frontend.

Uses cookie-based sessions stored server-side in memory.
The session token is stored in an HTTP cookie (read from ASGI scope)
and also in NiceGUI's client storage for logout purposes.
Passwords are hashed with SHA-256 (suitable for a personal project).

Environment variables (via pydantic-settings):
  BRAIN_AUTH_ENABLED  — true/false (default: true)
  BRAIN_AUTH_USERNAME — login username (default: admin)
  BRAIN_AUTH_PASSWORD — login password (default: changeme)
  BRAIN_AUTH_PASSWORD_HASH — pre-hashed password (optional, overrides password)
"""

from __future__ import annotations

import hashlib
import secrets
import time
import logging
from dataclasses import dataclass, field

from nicegui import ui

from backend.config import settings

logger = logging.getLogger(__name__)

SESSION_COOKIE = "brain_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days
SESSION_IDLE_MAX = 86400     # 24 hours idle timeout


# ── Session store ────────────────────────────────────────────────────

@dataclass
class Session:
    """A user session."""
    user: str
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_seen


_sessions: dict[str, Session] = {}


def _hash_password(password: str) -> str:
    """SHA-256 hash of a password."""
    return hashlib.sha256(password.encode()).hexdigest()


def _get_stored_hash() -> str:
    """Get the expected password hash from config."""
    if settings.auth_password_hash:
        return settings.auth_password_hash
    return _hash_password(settings.auth_password)


def verify_credentials(username: str, password: str) -> bool:
    """Verify username and password against config."""
    if not settings.auth_enabled:
        return True
    if username != settings.auth_username:
        return False
    return _hash_password(password) == _get_stored_hash()


def create_session(username: str) -> str:
    """Create a new session and return the session token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = Session(user=username)
    logger.info(f"Session created for {username}")
    return token


def get_session(token: str | None) -> Session | None:
    """Look up a session by token. Returns None if invalid/expired."""
    if not token:
        return None
    session = _sessions.get(token)
    if session is None:
        return None
    if session.age_seconds > SESSION_MAX_AGE:
        _sessions.pop(token, None)
        return None
    if session.idle_seconds > SESSION_IDLE_MAX:
        _sessions.pop(token, None)
        return None
    session.last_seen = time.time()
    return session


def destroy_session(token: str) -> None:
    """Destroy a session."""
    _sessions.pop(token, None)


def is_auth_enabled() -> bool:
    """Check if authentication is enabled."""
    return settings.auth_enabled


# ── Cookie helpers ──────────────────────────────────────────────────

def _read_cookie_from_scope(scope: dict) -> str | None:
    """Read the brain_session cookie from ASGI scope headers.

    ASGI headers are a list of (name, value) byte tuples.
    Cookies are sent as a single 'cookie' header with '; '-separated pairs.
    """
    headers = scope.get("headers", [])
    for name, value in headers:
        if name == b"cookie":
            cookie_str = value.decode("latin-1")
            for part in cookie_str.split(";"):
                part = part.strip()
                if part.startswith(f"{SESSION_COOKIE}="):
                    return part.split("=", 1)[1]
    return None


def _js_set_cookie(name: str, value: str, max_age: int) -> None:
    """Set a cookie via JavaScript."""
    ui.run_javascript(
        f'document.cookie = "{name}={value}; path=/; max-age={max_age}; samesite=Lax";'
    )


def _js_delete_cookie(name: str) -> None:
    """Delete a cookie via JavaScript."""
    ui.run_javascript(
        f'document.cookie = "{name}=; path=/; max-age=0";'
    )


# ── NiceGUI integration ──────────────────────────────────────────────

def require_auth():
    """Require authentication. Redirects to login if not authenticated.

    Reads the session token from the HTTP cookie in the ASGI scope,
    which is available on every page load (no async needed).
    Returns the session if authenticated.
    """
    if not is_auth_enabled():
        return Session(user="local")

    # Read token from HTTP cookie (sent with every request)
    token = None
    try:
        scope = ui.context.client.environ.get("asgi.scope", {})
        token = _read_cookie_from_scope(scope)
    except Exception:
        pass

    session = get_session(token)
    if session is not None:
        return session

    # Not authenticated — redirect to login
    current_path = "/"
    try:
        current_path = ui.context.client.environ.get("asgi.scope", {}).get("path", "/")
    except Exception:
        pass

    ui.navigate.to(f"/ui/login?next={current_path}")
    return Session(user="")


def set_session_cookie(token: str) -> None:
    """Store session token in HTTP cookie (via JS) and NiceGUI client storage."""
    # Set cookie via JavaScript so browser sends it with future requests
    _js_set_cookie(SESSION_COOKIE, token, SESSION_MAX_AGE)
    # Also store in client storage for logout
    try:
        ui.context.client.storage[SESSION_COOKIE] = token
    except Exception:
        pass


def clear_session_cookie() -> None:
    """Clear session cookie and client storage."""
    _js_delete_cookie(SESSION_COOKIE)
    try:
        del ui.context.client.storage[SESSION_COOKIE]
    except (KeyError, Exception):
        pass


def logout_current() -> None:
    """Log out the current user."""
    # Destroy server-side session
    token = None
    try:
        scope = ui.context.client.environ.get("asgi.scope", {})
        token = _read_cookie_from_scope(scope)
    except Exception:
        pass
    if token:
        destroy_session(token)
    clear_session_cookie()
    ui.navigate.to("/ui/login")
