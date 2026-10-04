"""Verifies the Telegram bot token actually works.

Reads the token from the environment/.env rather than the source tree so no
credential is ever written into the repository.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND = Path(__file__).resolve().parents[1]


def load_token() -> str:
    env_file = BACKEND / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def main() -> int:
    token = load_token()
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set")
        return 1

    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body[:300]}")
        return 1
    except Exception as exc:  # noqa: BLE001 - report any network failure
        print(f"request failed: {exc}")
        return 1

    if not payload.get("ok"):
        print(f"token rejected: {payload.get('description')}")
        return 1

    bot = payload["result"]
    print(f"bot: @{bot.get('username')}")
    print(f"name: {bot.get('first_name')}")
    print(f"bot_id: {bot.get('id')}")
    print("can_join_groups:", bot.get("can_join_groups"))
    print("token: VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())