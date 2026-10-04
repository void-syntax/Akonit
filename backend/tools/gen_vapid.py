"""Generates a VAPID key pair for web push.

Prints the keys so they can be pasted into .env. Nothing is written to the
repository: every subscribing device needs the same real key pair.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:  # pragma: no cover
    print("install cryptography: pip install cryptography")
    raise SystemExit(1) from None


def b64(data: bytes) -> str:
    """Unpadded URL-safe base64, which is what the Web Push spec expects."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def uncompressed_point(public_key) -> bytes:
    """SEC1 uncompressed encoding (0x04 || X || Y) for an EC public key."""
    numbers = public_key.public_numbers()
    return (
        b"\x04"
        + numbers.x.to_bytes(32, byteorder="big")
        + numbers.y.to_bytes(32, byteorder="big")
    )


def main() -> int:
    private_key = ec.generate_private_key(ec.SECP256R1())
    numbers = private_key.private_numbers()

    private_b64 = b64(numbers.private_value.to_bytes(32, byteorder="big"))
    public_b64 = b64(uncompressed_point(private_key.public_key()))

    print("VAPID_PUBLIC_KEY=" + public_b64)
    print("VAPID_PRIVATE_KEY=" + private_b64)
    print("VAPID_SUBJECT=mailto:admin@example.com")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())