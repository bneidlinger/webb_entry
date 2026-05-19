"""AWS SNS signature verification + canonical-string builder.

Reference: https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html

Only `SignatureVersion=1` (SHA1) and `=2` (SHA256) are supported. Cert URL must
live under `https://sns.<region>.amazonaws.com/` to refuse forged messages
pointing at attacker-controlled keys.
"""
from __future__ import annotations

import base64
import logging
import re
from typing import Any

import httpx

log = logging.getLogger(__name__)

_ALLOWED_CERT_URL = re.compile(
    r"^https://sns\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?/SimpleNotificationService-[A-Za-z0-9_-]+\.pem$"
)

_SUBSCRIPTION_FIELDS = (
    "Message",
    "MessageId",
    "SubscribeURL",
    "Timestamp",
    "Token",
    "TopicArn",
    "Type",
)
_NOTIFICATION_FIELDS = ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type")


def _canonical_string(msg: dict[str, Any]) -> bytes:
    msg_type = msg.get("Type")
    if msg_type in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        fields = _SUBSCRIPTION_FIELDS
    elif msg_type == "Notification":
        fields = _NOTIFICATION_FIELDS
    else:
        raise ValueError(f"Unsupported SNS message Type: {msg_type!r}")

    parts: list[str] = []
    for field in fields:
        if field == "Subject" and field not in msg:
            continue  # Subject is optional and only included if present
        if field not in msg:
            raise ValueError(f"Missing SNS field for canonical string: {field}")
        parts.append(field)
        parts.append(str(msg[field]))
    return ("\n".join(parts) + "\n").encode("utf-8")


def verify_signature(msg: dict[str, Any], *, http_client: httpx.Client | None = None) -> bool:
    """Return True iff `msg`'s SignatureVersion + Signature validate against its SigningCertURL.

    Network: fetches the cert from AWS. Caller can pass `http_client` for tests.
    """
    cert_url = msg.get("SigningCertURL", "")
    if not _ALLOWED_CERT_URL.match(cert_url):
        log.warning("SNS verify: rejected cert URL %r", cert_url)
        return False

    sig_version = msg.get("SignatureVersion")
    signature_b64 = msg.get("Signature")
    if not signature_b64 or sig_version not in ("1", "2"):
        log.warning("SNS verify: unsupported signature version %r", sig_version)
        return False

    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.x509 import load_pem_x509_certificate
    except ImportError:
        log.error("SNS verify: cryptography package not installed")
        return False

    client = http_client or httpx.Client(timeout=10.0)
    owns_client = http_client is None
    try:
        resp = client.get(cert_url)
        if resp.status_code != 200:
            log.warning("SNS verify: cert fetch returned %d", resp.status_code)
            return False
        cert_pem = resp.content
    finally:
        if owns_client:
            client.close()

    try:
        cert = load_pem_x509_certificate(cert_pem)
        public_key = cert.public_key()
        signature = base64.b64decode(signature_b64)
        canonical = _canonical_string(msg)
        algo = hashes.SHA256() if sig_version == "2" else hashes.SHA1()
        # SNS uses PKCS#1 v1.5 padding over RSA
        public_key.verify(  # type: ignore[union-attr]
            signature,
            canonical,
            padding.PKCS1v15(),
            algo,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("SNS verify: signature check failed: %s", exc)
        return False
