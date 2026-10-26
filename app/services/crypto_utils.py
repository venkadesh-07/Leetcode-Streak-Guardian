"""
Cryptographic Utilities for LeetCode Streak Guardian.
Provides authenticated symmetric encryption at rest for sensitive credentials
(e.g., LeetCode session cookies and CSRF tokens) using AES-strength CTR mode with HMAC-SHA256
(Encrypt-then-MAC). Zero external C-dependencies; 100% standard library.
"""

import base64
import hashlib
import hmac
import os
import secrets
import logging
from flask import current_app, has_app_context

logger = logging.getLogger(__name__)

CIPHER_PREFIX = "enc:v1:"


def _get_encryption_secret() -> str:
    """Retrieve the application secret key for key derivation."""
    secret = os.environ.get("COOKIE_ENCRYPTION_KEY", "").strip()
    if not secret and has_app_context():
        secret = current_app.config.get("SECRET_KEY", "").strip()
    if not secret:
        secret = os.environ.get("SECRET_KEY", "").strip()
    if not secret:
        # Fallback to prevent unhandled crash in test/isolated environments
        secret = "streak-guardian-default-cookie-key-must-be-configured"
    return secret


def _derive_keys(secret: str, salt: bytes):
    """
    HKDF-style key expansion using HMAC-SHA256.
    Derives two cryptographically distinct 256-bit keys:
      - k_enc: For keystream generation
      - k_mac: For Encrypt-then-MAC authentication
    """
    prk = hmac.new(salt, secret.encode("utf-8"), hashlib.sha256).digest()
    k_enc = hmac.new(prk, b"leetcode-guardian-enc-v1", hashlib.sha256).digest()
    k_mac = hmac.new(prk, b"leetcode-guardian-mac-v1", hashlib.sha256).digest()
    return k_enc, k_mac


def encrypt_cookie(plaintext: str) -> str:
    """
    Encrypts a plaintext cookie string into an authenticated ciphertext string.
    Format: 'enc:v1:<base64(salt[16] + nonce[16] + tag[32] + ciphertext)>'
    """
    if not plaintext:
        return ""
    plaintext = str(plaintext).strip()
    if not plaintext:
        return ""
    if plaintext.startswith(CIPHER_PREFIX):
        return plaintext  # Already encrypted

    secret = _get_encryption_secret()
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    k_enc, k_mac = _derive_keys(secret, salt)

    data = plaintext.encode("utf-8")
    blocks = []
    # Generate keystream using HMAC-SHA256 in Counter (CTR) mode
    for i in range((len(data) + 31) // 32):
        counter = i.to_bytes(4, "big")
        ks = hmac.new(k_enc, nonce + counter, hashlib.sha256).digest()
        blocks.append(ks)
    keystream = b"".join(blocks)[:len(data)]
    ciphertext = bytes(a ^ b for a, b in zip(data, keystream))

    # Authenticate via HMAC-SHA256 over salt + nonce + ciphertext (Encrypt-then-MAC)
    tag = hmac.new(k_mac, salt + nonce + ciphertext, hashlib.sha256).digest()
    payload = salt + nonce + tag + ciphertext
    return CIPHER_PREFIX + base64.urlsafe_b64encode(payload).decode("ascii")


def decrypt_cookie(ciphertext_str: str) -> str:
    """
    Decrypts an authenticated ciphertext string back into plaintext.
    Gracefully handles unencrypted legacy strings for backward compatibility.
    """
    if not ciphertext_str:
        return ""
    ciphertext_str = str(ciphertext_str).strip()
    if not ciphertext_str:
        return ""

    # Backward compatibility: legacy plaintext strings pass through safely
    if not ciphertext_str.startswith(CIPHER_PREFIX):
        return ciphertext_str

    try:
        raw_b64 = ciphertext_str[len(CIPHER_PREFIX):].encode("ascii")
        payload = base64.urlsafe_b64decode(raw_b64)
        if len(payload) < 16 + 16 + 32:
            logger.warning("decrypt_cookie: Ciphertext payload is truncated.")
            return ""

        salt = payload[:16]
        nonce = payload[16:32]
        tag = payload[32:64]
        ciphertext = payload[64:]

        secret = _get_encryption_secret()
        k_enc, k_mac = _derive_keys(secret, salt)

        # Constant-time MAC verification
        expected_tag = hmac.new(k_mac, salt + nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            logger.error("decrypt_cookie: HMAC integrity check failed. Data may be tampered with or key changed.")
            return ""

        # Decrypt CTR keystream
        blocks = []
        for i in range((len(ciphertext) + 31) // 32):
            counter = i.to_bytes(4, "big")
            ks = hmac.new(k_enc, nonce + counter, hashlib.sha256).digest()
            blocks.append(ks)
        keystream = b"".join(blocks)[:len(ciphertext)]
        plaintext_bytes = bytes(a ^ b for a, b in zip(ciphertext, keystream))
        return plaintext_bytes.decode("utf-8")
    except Exception as exc:
        logger.error(f"decrypt_cookie: Decryption error ({exc})")
        return ""
