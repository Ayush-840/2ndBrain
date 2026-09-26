"""Encrypted at-rest storage for original document bytes.

Episodic text embeddings are lower-risk, but the originals that arrive over
WhatsApp (IDs, medical reports, payslips) are not — so they are encrypted
before touching disk.

Key resolution order:
  1. BRAIN_BLOB_KEY            — a Fernet key (best: rotate it yourself)
  2. BRAIN_BLOB_KEY            — any other string → PBKDF2-derived Fernet key
  3. neither                   — generate once, persist to data/.blob_key (0600)

The point is that documents are never written to disk in plaintext, without
requiring the user to think about key management on day one.
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from backend.config import settings

logger = logging.getLogger(__name__)

_KEY_FILE = ".blob_key"


def _derive_fernet_key(secret: str) -> bytes:
    """Turn an arbitrary passphrase into a urlsafe-base64 Fernet key."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"2ndbrain-blob-store-v1",
        iterations=390_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


def _is_fernet_key(secret: str) -> bool:
    """True when the string is already a urlsafe-base64 32-byte Fernet key."""
    if not secret:
        return False
    try:
        Fernet(secret.encode())
        return True
    except (ValueError, TypeError):
        return False


class BlobStore:
    """Encrypts original files into ``settings.blob_dir``."""

    def __init__(self, directory: Path | str | None = None, key: str | None = None):
        self.directory = Path(directory) if directory else settings.blob_dir
        secret = settings.blob_key if key is None else key
        self._fernet = Fernet(self._resolve_key(secret))
        self.key_source = self._key_source(secret)

    # ── key handling ─────────────────────────────────────────────────

    def _resolve_key(self, secret: str) -> bytes:
        if _is_fernet_key(secret):
            return secret.encode()

        if secret:
            return _derive_fernet_key(secret)

        # No key configured: generate once and persist locally (0600).
        self.directory.mkdir(parents=True, exist_ok=True)
        key_path = self.directory.parent / _KEY_FILE
        if key_path.exists():
            return key_path.read_text().strip().encode()

        new_key = Fernet.generate_key()
        key_path.write_text(new_key.decode())
        try:
            os.chmod(key_path, 0o600)
        except OSError:  # pragma: no cover — non-POSIX filesystems
            pass
        logger.warning(
            "No BRAIN_BLOB_KEY set — generated a local encryption key at %s. "
            "Back it up: losing it means losing the ability to read stored documents.",
            key_path,
        )
        return new_key

    def _key_source(self, secret: str) -> str:
        if not secret:
            return "generated-file"
        return "env-fernet-key" if _is_fernet_key(secret) else "env-passphrase"

    # ── storage ──────────────────────────────────────────────────────

    def put(self, data: bytes, *, doc_id: str, suffix: str = ".bin") -> str:
        """Encrypt ``data`` and return its path relative to the data dir."""
        if not suffix.startswith("."):
            suffix = "." + suffix
        self.directory.mkdir(parents=True, exist_ok=True)
        filename = f"{doc_id}{suffix}"
        path = self.directory / filename
        path.write_bytes(self._fernet.encrypt(data))
        try:
            os.chmod(path, 0o600)
        except OSError:  # pragma: no cover
            pass
        return f"{self.directory.name}/{filename}"

    def get(self, relative_path: str) -> bytes:
        """Decrypt a blob previously written by :meth:`put`."""
        path = Path(relative_path)
        if not path.is_absolute():
            path = self.directory.parent / relative_path
        try:
            return self._fernet.decrypt(path.read_bytes())
        except InvalidToken as exc:
            raise ValueError(f"Cannot decrypt {relative_path}: wrong blob key") from exc
        except FileNotFoundError:
            raise FileNotFoundError(f"No stored document at {relative_path}") from None

    def exists(self, relative_path: str) -> bool:
        path = Path(relative_path)
        if not path.is_absolute():
            path = self.directory.parent / relative_path
        return path.exists()


def new_doc_id() -> str:
    return secrets.token_hex(8)
