"""Tests for src.infrastructure.crypto — Fernet round-trip + missing-key handling."""
import pytest

from src.infrastructure import crypto


def test_round_trip_with_key():
    key = crypto.generate_key()
    cipher = crypto.encrypt("sk-test-1234567890", key=key)
    assert cipher != "sk-test-1234567890"
    plain = crypto.decrypt(cipher, key=key)
    assert plain == "sk-test-1234567890"


def test_decrypt_with_wrong_key_raises():
    cipher = crypto.encrypt("hello", key=crypto.generate_key())
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(cipher, key=crypto.generate_key())


def test_encrypt_without_key_raises():
    with pytest.raises(crypto.CryptoError, match="encryption key not configured"):
        crypto.encrypt("hello", key=None)


def test_invalid_key_raises():
    with pytest.raises(crypto.CryptoError, match="invalid encryption key"):
        crypto.encrypt("hello", key="not-a-fernet-key")
