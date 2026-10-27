"""Encryption helpers for credentials stored in the local application database."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    key = settings.telegram_token_encryption_key
    if not key:
        raise RuntimeError(
            "Telegram token storage is unavailable: set TELEGRAM_TOKEN_ENCRYPTION_KEY"
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("TELEGRAM_TOKEN_ENCRYPTION_KEY is invalid") from exc


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("Could not decrypt stored Telegram bot token") from exc
