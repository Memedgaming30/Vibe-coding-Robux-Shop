"""
Webhook signature verification.

INVARIANT: verify against the exact raw bytes received, BEFORE parsing,
with a constant-time comparison (hmac.compare_digest).
"""
import hmac
import hashlib


def verify_webhook(raw_body: bytes, signature_hex: str, secret: str) -> bool:
    if not raw_body or not signature_hex or not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature_hex, expected)
