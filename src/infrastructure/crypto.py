"""Fernet symmetric encryption for boss-supplied credentials.

The encryption key is read from `Settings.boss_credential_encryption_key`
(env var). If unset, encryption / decryption raise `CryptoError` rather than
silently degrading to plaintext.

Key generation (one-off, save the output to env):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class CryptoError(Exception):
    """Raised when encryption / decryption fails or key is missing."""


def generate_key() -> str:
    """Return a fresh Fernet key as a 44-char base64 string."""
    return Fernet.generate_key().decode()


def _fernet(key: str | None) -> Fernet:
    if not key:
        raise CryptoError("encryption key not configured")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise CryptoError(f"invalid encryption key: {exc}") from exc


def encrypt(plain: str, *, key: str | None) -> str:
    """Encrypt `plain` with `key` (Fernet, base64). Returns ASCII ciphertext."""
    return _fernet(key).encrypt(plain.encode()).decode()


def decrypt(cipher: str, *, key: str | None) -> str:
    """Decrypt `cipher` produced by `encrypt`. Raises CryptoError on bad token."""
    try:
        return _fernet(key).decrypt(cipher.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("decryption failed (wrong key or tampered ciphertext)") from exc
