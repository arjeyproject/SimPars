"""Local Sintel catalog synchronization and pricing."""
from __future__ import annotations
import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
import database as db
from services.sintel import SintelClient, SintelError, _humanize_error, invalidate_catalog_cache

log = logging.getLogger(__name__)
SERVICE_CATEGORIES = {
    "telegram": {"emoji": "👥", "title": "سرویس‌های تلگرام", "subcategories": {
        "members": {"emoji": "👥", "title": "اعضای کانال و گروه", "keywords": ["member", "subscriber", "عضو", "مشترک"]},
        "views": {"emoji": "👁️", "title": "بازدید پست", "keywords": ["view", "بازدید"]},
        "reactions": {"emoji": "❤️", "title": "ریاکشن و احساس", "keywords": ["reaction", "ریاکشن"]},
        "comments": {"emoji": "💬", "title": "کامنت و نظر", "keywords": ["comment", "کامنت"]},
        "shares": {"emoji": "📤", "title": "اشتراک‌گذاری", "keywords": ["share", "اشتراک"]},
        "other": {"emoji": "📊", "title": "سایر سرویس‌ها", "keywords": []}}},
    "instagram": {"emoji": "📸", "title": "سرویس‌های اینستاگرام", "subcategories": {
        "followers": {"emoji": "👥", "title": "فالوور", "keywords": ["followers", "فالوور", "follower"]},
        "likes": {"emoji": "❤️", "title": "لایک", "keywords": ["like", "لایک"]},
        "views": {"emoji": "👁️", "title": "بازدید", "keywords": ["view", "بازدید", "reel", "ریلز"]},
        "comments": {"emoji": "💬", "title": "کامنت", "keywords": ["comment", "کامنت"]},
        "story": {"emoji": "📱", "title": "استوری", "keywords": ["story", "استوری"]},
        "other": {"emoji": "📊", "title": "سایر سرویس‌ها", "keywords": []}}}}


def _subcategory(platform: str, name: str, category: str) -> str:
    text = f"{name} {category}".lower()
    for key, info in SERVICE_CATEGORIES.get(platform, {}).get("subcategories", {}).items():
        if key != "other" and any(k.lower() in text for k in info["keywords"]):
            return key
    return "other"


def calculate_order_price(rate: str | float, quantity: int) -> int:
    try:
        return int((Decimal(str(rate)) * Decimal(str(quantity)) / Decimal("1000")).quantize(Decimal("1")))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def calculate_selling_price(provider_cost: int, profit_percent: float) -> int:
    return max(0, int(provider_cost + provider_cost * float(profit_percent) / 100))


async def sync_catalog_from_provider(api_key: str) -> dict[str, Any]:
    try:
        services = await SintelClient(api_key).get_services(use_cache=False)
        if not services:
            return {"success": False, "error": "کاتالوگ سینتل خالی است", "total": 0}
        ids = []
        counts = {"telegram": 0, "instagram": 0, "unknown": 0}
        for service in services:
            sid = int(service.get("service", 0))
            if not sid:
                continue
            platform = service.get("_platform", "telegram")
            subcat = _subcategory(platform, service.get("name", ""), service.get("category", ""))
            extra = json.dumps({"type": service.get("type", ""), "category": service.get("category", ""), "platform": platform, "subcategory": subcat, "refill": bool(service.get("refill", False)), "cancel": bool(service.get("cancel", False)), "description": service.get("description", "")}, ensure_ascii=False)
            await db._db.execute("""INSERT INTO sintel_services(service_id,name,rate,min_quantity,max_quantity,platform,subcategory,extra_data,is_active,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?) ON CONFLICT(service_id) DO UPDATE SET name=excluded.name,rate=excluded.rate,min_quantity=excluded.min_quantity,max_quantity=excluded.max_quantity,platform=excluded.platform,subcategory=excluded.subcategory,extra_data=excluded.extra_data,is_active=1,updated_at=excluded.updated_at""", (sid, service.get("name", "سرویس"), service.get("rate", "0"), int(service.get("min", 0)), int(service.get("max", 0)), platform, subcat, extra, int(datetime.now().timestamp())))
            ids.append(sid)
            counts[platform] = counts.get(platform, 0) + 1
        if ids:
            marks = ",".join("?" for _ in ids)
            await db._db.execute(f"UPDATE sintel_services SET is_active=0 WHERE service_id NOT IN ({marks})", tuple(ids))
        await db._db.commit()
        invalidate_catalog_cache()
        return {"success": True, "total": len(ids), **counts}
    except SintelError as exc:
        log.warning("Sintel sync failed: %s", exc)
        return {"success": False, "error": _humanize_error(exc), "total": 0}
    except Exception as exc:
        log.exception("Sintel sync failed")
        return {"success": False, "error": f"خطای داخلی: {exc}", "total": 0}


async def get_catalog_by_subcategory(platform: str, subcategory: str):
    async with db._db.execute("SELECT * FROM sintel_services WHERE platform=? AND subcategory=? AND is_active=1 ORDER BY name", (platform, subcategory)) as cur:
        return [dict(row) for row in await cur.fetchall()]


async def get_cached_catalog(platform: str | None = None):
    sql = "SELECT * FROM sintel_services WHERE is_active=1" + (" AND platform=?" if platform else "") + " ORDER BY platform,subcategory,name"
    async with db._db.execute(sql, (platform,) if platform else ()) as cur:
        return [dict(row) for row in await cur.fetchall()]


async def get_service_by_id(service_id: int):
    async with db._db.execute("SELECT * FROM sintel_services WHERE service_id=? AND is_active=1", (int(service_id),)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None
