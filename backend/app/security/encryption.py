"""AES-256-GCM encryption at rest for small secrets (D8.5: TOTP secrets),
keyed by `settings().encryption_key` (32 raw bytes, hex-encoded in .env
per .env.example's own comment -- declared since Phase 1 but unused by
any module until this one).
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


class EncryptionNotConfigured(Exception):
    pass


def _key() -> bytes:
    hex_key = settings().encryption_key
    if not hex_key:
        raise EncryptionNotConfigured("ENCRYPTION_KEY is not set.")
    key = bytes.fromhex(hex_key)
    if len(key) != 32:
        raise EncryptionNotConfigured("ENCRYPTION_KEY must be 32 bytes (64 hex characters) for AES-256.")
    return key


def encrypt(plaintext: str) -> str:
    """Returns base64(nonce || ciphertext_with_tag), safe to store as text."""
    aesgcm = AESGCM(_key())
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str) -> str:
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(_key())
    return aesgcm.decrypt(nonce, ciphertext, associated_data=None).decode("utf-8")
