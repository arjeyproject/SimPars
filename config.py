"""SimPars configuration loaded from environment."""
from __future__ import annotations

import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _parse_ids(value: str) -> list[int]:
    ids: list[int] = []
    for part in value.replace(" ", "").split(","):
        if part.isdigit():
            ids.append(int(part))
    return ids


def _int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, "") or default))
    except ValueError:
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = _parse_ids(os.getenv("ADMIN_IDS", ""))
BOT_USERNAME = os.getenv("BOT_USERNAME", "SimParsBot").strip().lstrip("@")
CHANNEL_USERNAME = "@" + os.getenv("CHANNEL_USERNAME", "SimPars").strip().lstrip("@")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "iRezaFattahi").strip().lstrip("@")
INSTAGRAM_ID = os.getenv("INSTAGRAM_ID", "SimPars.ir").strip().lstrip("@")
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0").strip()
WEB_PORT = int(os.getenv("WEB_PORT", "8080") or 8080)
BASE_URL = os.getenv("BASE_URL", "").strip().rstrip("/")
_db_path = os.getenv("DB_PATH", "data/simpars.db").strip() or "data/simpars.db"
DB_PATH = _db_path if os.path.isabs(_db_path) else os.path.join(BASE_DIR, _db_path)

# ZarinPal (v4). Values in .env take priority over the admin-panel settings.
# ZARINPAL_SANDBOX: "1" force sandbox, "0" force production, empty = admin toggle.
ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID", "").strip()
ZARINPAL_SANDBOX = os.getenv("ZARINPAL_SANDBOX", "").strip()
ZARINPAL_CALLBACK_URL = os.getenv("ZARINPAL_CALLBACK_URL", "").strip().rstrip("/")
ZARINPAL_TIMEOUT = _int("ZARINPAL_TIMEOUT", 20)
# A pending invoice for the exact same number/price is reused inside this window
# instead of opening a second gateway request (double clicks, retries).
INVOICE_REUSE_SECONDS = _int("INVOICE_REUSE_SECONDS", 600)

# Optional Bot API 9.4 custom emoji IDs. Leave empty until valid IDs are supplied.
PREMIUM_EMOJI_SUCCESS = os.getenv("PREMIUM_EMOJI_SUCCESS", "").strip() or None
PREMIUM_EMOJI_DANGER = os.getenv("PREMIUM_EMOJI_DANGER", "").strip() or None
PREMIUM_EMOJI_PRIMARY = os.getenv("PREMIUM_EMOJI_PRIMARY", "").strip() or None

ORDER_LIFETIME = 20 * 60
CHECK_INTERVAL = 8
MARKET_INTERVAL = int(os.getenv("MARKET_INTERVAL", "86400") or 86400)
