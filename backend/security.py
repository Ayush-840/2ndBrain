"""Launch-blocking security checks (PRD 6.2 / TRD §7).

Once payslips, IDs and medical PDFs flow through the webhook, defaults like
``admin``/``changeme`` and an unsigned endpoint are the difference between a
toy and a system holding sensitive personal data.

``validate_security()`` runs at startup and refuses to boot when the posture
is unsafe. ``BRAIN_ALLOW_INSECURE=true`` is the explicit, logged opt-out for
local experiments with no real documents in them.
"""

from __future__ import annotations

import logging
import os

from backend.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_PASSWORDS = {"changeme", "admin", "password", "123456", ""}


def security_problems() -> list[str]:
    """Return a list of blocking problems (empty = safe to start)."""
    problems: list[str] = []

    webhook_live = settings.whatsapp_enabled

    if webhook_live:
        # Every TRD §7 requirement for the inbound channel.
        if not settings.whatsapp_app_secret:
            problems.append(
                "BRAIN_WHATSAPP_APP_SECRET is not set — webhook signatures "
                "(X-Hub-Signature-256) cannot be verified, so anyone who finds "
                "the URL could inject documents."
            )
        if not settings.whatsapp_allowed_sender:
            problems.append(
                "BRAIN_WHATSAPP_ALLOWED_SENDER is not set — inbound messages "
                "from any number would be accepted."
            )
        if not settings.whatsapp_verify_token:
            problems.append("BRAIN_WHATSAPP_VERIFY_TOKEN is not set — handshake would always 403.")
        if settings.whatsapp_allow_unsigned:
            problems.append(
                "BRAIN_WHATSAPP_ALLOW_UNSIGNED=true disables signature checks. "
                "Only acceptable on an isolated local experiment."
            )

        # The system now holds sensitive documents → real auth is required.
        if not settings.auth_enabled:
            problems.append(
                "BRAIN_AUTH_ENABLED=false while the WhatsApp webhook is live. "
                "Enable auth (and set a real password) before sending real documents."
            )
        password = settings.auth_password
        if settings.auth_enabled and not settings.auth_password_hash and password in _DEFAULT_PASSWORDS:
            problems.append(
                "BRAIN_AUTH_PASSWORD is still a default value. Set "
                "BRAIN_AUTH_PASSWORD_HASH (or a strong BRAIN_AUTH_PASSWORD) "
                "before the webhook is reachable."
            )

    if (
        not problems
        and not settings.whatsapp_enabled
        and settings.auth_enabled
        and not settings.auth_password_hash
        and settings.auth_password in _DEFAULT_PASSWORDS
    ):
        # No webhook: only warn about default credentials if auth is on.
        logger.warning(
            "Auth is enabled with a default password — set BRAIN_AUTH_PASSWORD_HASH."
        )

    return problems


def validate_security(*, bind_host: str | None = None) -> None:
    """Raise RuntimeError when the current configuration is unsafe.

    Args:
        bind_host: Host the server binds to. Defaults to BRAIN_BIND_HOST or
            0.0.0.0 (main.py's own default). Non-localhost binds are held to
            the stricter standard even without a webhook.
    """
    if settings.allow_insecure:
        logger.warning(
            "BRAIN_ALLOW_INSECURE=true — skipping all security checks. "
            "Never do this with real personal documents."
        )
        return

    problems = security_problems()

    host = bind_host or os.environ.get("BRAIN_BIND_HOST", "0.0.0.0")
    localhost = host in ("127.0.0.1", "::1", "localhost")
    if not localhost and settings.auth_enabled and not settings.auth_password_hash and settings.auth_password in _DEFAULT_PASSWORDS:
        problems.append(
            f"Binding to {host} with default credentials — set BRAIN_AUTH_PASSWORD_HASH."
        )

    if problems:
        raise RuntimeError(
            "Refusing to start — security requirements not met (PRD 6.2):\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\n\nSet BRAIN_ALLOW_INSECURE=true only for local experiments."
        )
