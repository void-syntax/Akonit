from datetime import UTC, datetime, timedelta

from app.bot import telegram_bot


def test_saved_profile_token_takes_precedence_over_environment(monkeypatch):
    monkeypatch.setattr(
        "app.core.secrets.decrypt_secret", lambda value: f"decrypted:{value}"
    )

    assert telegram_bot._select_token(["encrypted"], "environment") == "decrypted:encrypted"


def test_environment_token_is_fallback_when_no_profile_token():
    assert telegram_bot._select_token([None, ""], "environment") == "environment"
    assert telegram_bot._select_token([], None) is None


def test_recent_start_chat_can_be_found_without_polling_telegram():
    telegram_bot._recent_private_chats.clear()
    telegram_bot.remember_private_chat("test-token", 12345, "Test User")

    assert telegram_bot.find_recent_private_chat("test-token") == ("12345", "Test User")


def test_recent_start_chat_expires():
    token = "expired-test-token"
    key = telegram_bot.hashlib.sha256(token.encode("utf-8")).hexdigest()
    telegram_bot._recent_private_chats[key] = (
        datetime.now(UTC) - timedelta(minutes=11), "12345", "Test User"
    )

    assert telegram_bot.find_recent_private_chat(token) is None
