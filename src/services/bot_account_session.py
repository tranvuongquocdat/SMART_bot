"""Symmetric Fernet wrap for ``bot_accounts.credentials_blob_enc``.

Session blob shape (Zalo): ``{cookie, imei, userAgent}`` — output of
``src/channels/zalo/bridge/login.js``. Never logged in cleartext.
"""

from __future__ import annotations

import json

from cryptography.fernet import Fernet

from src.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.FERNET_KEY.encode())
    return _fernet


def encrypt_credentials(session: dict) -> bytes:
    return _get_fernet().encrypt(json.dumps(session).encode())


def decrypt_credentials(blob: bytes) -> dict:
    return json.loads(_get_fernet().decrypt(bytes(blob)))
