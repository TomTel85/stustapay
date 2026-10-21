"""Admin MFA cryptographic helpers. Seeds are encrypted with the server secret key."""

import base64
import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA1
from cryptography.hazmat.primitives.twofactor.totp import TOTP


def encrypt_secret(secret: str, *, key: str, user_id: int) -> bytes:
    nonce = secrets.token_bytes(12)
    cipher = AESGCM(hashlib.sha256(b"stustapay-admin-mfa-v1:" + key.encode()).digest())
    return nonce + cipher.encrypt(nonce, secret.encode(), str(user_id).encode())


def decrypt_secret(value: bytes, *, key: str, user_id: int) -> str:
    cipher = AESGCM(hashlib.sha256(b"stustapay-admin-mfa-v1:" + key.encode()).digest())
    return cipher.decrypt(value[:12], value[12:], str(user_id).encode()).decode()


def totp_for_secret(secret: str) -> TOTP:
    return TOTP(base64.b32decode(secret), 6, SHA1(), 30)


def match_totp(secret: str, code: str, *, now: float, last_step: int) -> int | None:
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    totp = totp_for_secret(secret)
    step = int(now) // 30
    for candidate in (step, step - 1, step + 1):
        if candidate > last_step and secrets.compare_digest(totp.generate(candidate * 30), code.encode()):
            return candidate
    return None


def recovery_digest(code: str) -> str:
    return hashlib.sha256(code.strip().replace("-", "").upper().encode()).hexdigest()
