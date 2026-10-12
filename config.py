"""SimPars configuration loaded from environment."""
from __future__ import annotations
import os
from dotenv import load_dotenv
BASE_DIR=os.path.dirname(os.path.abspath(__file__)); load_dotenv(os.path.join(BASE_DIR,".env"))
def _parse_ids(value): return [int(part) for part in value.replace(" ","").split(",") if part.isdigit()]
BOT_TOKEN=os.getenv("BOT_TOKEN","").strip(); ADMIN_IDS=_parse_ids(os.getenv("ADMIN_IDS","8516792883")); BOT_USERNAME=os.getenv("BOT_USERNAME","SimParsBot").strip().lstrip("@"); CHANNEL_USERNAME="@"+os.getenv("CHANNEL_USERNAME","SimPars").strip().lstrip("@"); OWNER_USERNAME=os.getenv("OWNER_USERNAME","iRezaFattahi").strip().lstrip("@"); INSTAGRAM_ID=os.getenv("INSTAGRAM_ID","SimPars.ir").strip().lstrip("@"); WEB_HOST=os.getenv("WEB_HOST","0.0.0.0").strip(); WEB_PORT=int(os.getenv("WEB_PORT","8080") or 8080); BASE_URL=os.getenv("BASE_URL","").strip().rstrip("/")
_db_path=os.getenv("DB_PATH","data/simpars.db").strip() or "data/simpars.db"; DB_PATH=_db_path if os.path.isabs(_db_path) else os.path.join(BASE_DIR,_db_path)
ORDER_LIFETIME=20*60; CHECK_INTERVAL=8
# Navasan is rate-limited; refresh every 12h by default. Override with 86400 for daily updates.
MARKET_INTERVAL=int(os.getenv("MARKET_INTERVAL","43200") or 43200)
