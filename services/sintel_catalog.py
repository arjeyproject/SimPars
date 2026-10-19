"""Live Panelix catalog, dynamic categories, and guarded pricing."""
from __future__ import annotations
import asyncio, json, logging, time
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any
import database as db
from services.sintel import PanelixClient, PanelixError, _humanize_error

log = logging.getLogger(__name__)
_sync_lock = asyncio.Lock()
PLATFORM_LABELS = {
    "instagram": ("📸", "اینستاگرام"), "telegram": ("✈️", "تلگرام"), "threads": ("🧵", "تردز"),
    "whatsapp": ("🟢", "واتساپ"), "rubika": ("🟣", "روبیکا"), "eitaa": ("🟠", "ایتا"),
    "aparat": ("▶️", "آپارات"), "youtube": ("▶️", "یوتیوب"), "facebook": ("🔵", "فیسبوک"),
    "twitter": ("🐦", "توییتر / ایکس"), "spotify": ("🎧", "اسپاتیفای"), "tiktok": ("🎵", "تیک‌تاک"),
    "other": ("📱", "سایر شبکه‌های اجتماعی"),
}


def _text(*values: Any) -> str:
    return " ".join(str(v or "") for v in values).lower()


def classify_platform(name: str, category: str, description: str = "") -> str:
    text = _text(name, category, description)
    for key, markers in {
        "instagram": ("instagram", "اینستا", "فالوور اینست"), "telegram": ("telegram", "تلگرام", "t.me"),
        "threads": ("threads", "تردز"), "whatsapp": ("whatsapp", "واتساپ"), "rubika": ("rubika", "روبیکا", "روبینو"),
        "eitaa": ("eitaa", "ایتا"), "aparat": ("aparat", "آپارات"), "youtube": ("youtube", "یوتیوب"),
        "facebook": ("facebook", "فیسبوک"), "twitter": ("twitter", "توییتر", "x.com"),
        "spotify": ("spotify", "اسپاتیفای"), "tiktok": ("tiktok", "تیک تاک", "تیک‌تاک"),
    }.items():
        if any(marker in text for marker in markers): return key
    return "other"


def _subcategory(name: str, category: str, description: str = "") -> str:
    text = _text(name, category, description)
    for key, markers in {
        "followers": ("follower", "فالوور", "member", "ممبر", "subscriber", "عضو"),
        "likes": ("like", "لایک"), "views": ("view", "بازدید", "play", "پخش"),
        "comments": ("comment", "کامنت"), "story": ("story", "استوری"), "reactions": ("reaction", "ری‌اکشن", "واکنش"),
        "boost": ("boost", "بوست"), "shares": ("share", "اشتراک", "سیو"), "watch": ("watch", "تماشا"),
    }.items():
        if any(marker in text for marker in markers): return key
    return "other"


def category_label(platform: str, subcategory: str) -> str:
    names = {"followers":"فالوور و ممبر", "likes":"لایک", "views":"بازدید و پخش", "comments":"کامنت", "story":"استوری", "reactions":"ری‌اکشن", "boost":"بوست", "shares":"سیو و اشتراک‌گذاری", "watch":"زمان تماشا", "other":"سایر خدمات"}
    return names.get(subcategory, "سایر خدمات")


def _verified_price(rate: str, quantity: int, profit: str, unit: str, currency: str, fx_rate: float) -> int:
    if unit not in ("per_1000", "per_order") or not currency or currency == "unverified": return 0
    try:
        base = Decimal(rate) * (Decimal(quantity) / Decimal(1000) if unit == "per_1000" else Decimal(1))
        if currency.upper() == "USD": base *= Decimal(str(fx_rate))
        elif currency.upper() not in ("IRR", "IRT", "TOMAN", "تومان"): return 0
        return int((base * (Decimal(1) + Decimal(profit or "0") / Decimal(100))).quantize(Decimal("1"), rounding=ROUND_CEILING))
    except (InvalidOperation, TypeError, ValueError): return 0


def calculate_order_price(rate: str | float, quantity: int, *, unit: str = "unverified", currency: str = "", fx_rate: float = 0, profit: str = "0") -> int:
    return _verified_price(str(rate), int(quantity), str(profit), unit, currency, fx_rate)


def calculate_selling_price(provider_cost: int, profit_percent: float) -> int:
    return max(0, int(Decimal(provider_cost) * (Decimal(1) + Decimal(str(profit_percent)) / Decimal(100))))


async def sync_catalog_from_provider(api_key: str) -> dict[str, Any]:
    async with _sync_lock:
        started = int(time.time())
        try:
            services = await PanelixClient(api_key).get_services()
            if not services:
                raise PanelixError("empty or invalid services response; last valid catalog preserved")
            unit = await db.get_setting("panelix_rate_unit")
            currency = await db.get_setting("panelix_currency")
            now = int(time.time()); incoming = {int(s["service"]): s for s in services}; counts = {"new": 0, "updated": 0, "unavailable": 0, "errors": 0}
            for sid, service in incoming.items():
                platform = classify_platform(service["name"], service["category"], service["description"])
                sub = _subcategory(service["name"], service["category"], service["description"])
                raw = json.dumps(service, ensure_ascii=False, sort_keys=True)
                async with db._db.execute("SELECT * FROM sintel_services WHERE service_id=?", (sid,)) as cur: old = await cur.fetchone()
                verified = int(unit in ("per_1000", "per_order") and bool(currency and currency != "unverified"))
                if old is None:
                    counts["new"] += 1
                    await db._db.execute("INSERT INTO sintel_services(service_id,name,rate,min_quantity,max_quantity,platform,subcategory,extra_data,is_active,updated_at,provider,currency,rate_unit,price_verified,provider_category,provider_type,description,display_name,last_seen_at,unavailable_reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (sid,service["name"],service["rate"],service["min"],service["max"],platform,sub,raw,1,now,"panelix",currency,unit,verified,service["category"],service["type"],service["description"],"",now,""))
                else:
                    changed = any(str(old[k]) != str(v) for k, v in (("name",service["name"]),("rate",service["rate"]),("min_quantity",service["min"]),("max_quantity",service["max"]),("extra_data",raw),("platform",platform),("subcategory",sub)))
                    if changed: counts["updated"] += 1
                    await db._db.execute("UPDATE sintel_services SET name=?,rate=?,min_quantity=?,max_quantity=?,platform=?,subcategory=?,extra_data=?,is_active=1,updated_at=?,provider='panelix',currency=?,rate_unit=?,price_verified=?,provider_category=?,provider_type=?,description=?,last_seen_at=?,unavailable_reason='' WHERE service_id=?", (service["name"],service["rate"],service["min"],service["max"],platform,sub,raw,now,currency,unit,verified,service["category"],service["type"],service["description"],now,sid))
            marks = ",".join("?" for _ in incoming)
            async with db._db.execute(f"SELECT service_id FROM sintel_services WHERE provider='panelix' AND is_active=1 AND service_id NOT IN ({marks})", tuple(incoming)) as cur: removed = [r[0] for r in await cur.fetchall()]
            if removed:
                counts["unavailable"] = len(removed)
                await db._db.executemany("UPDATE sintel_services SET is_active=0, unavailable_reason=?, updated_at=? WHERE service_id=?", [("در فهرست فعلی پنلیکس نیست", now, sid) for sid in removed])
            result = {"success": True, "total": len(incoming), **counts}
            await db._db.execute("INSERT INTO panelix_sync_log(started_at,finished_at,success,total,new_count,updated_count,unavailable_count,detail) VALUES(?,?,?,?,?,?,?,?)", (started,now,1,len(incoming),counts["new"],counts["updated"],counts["unavailable"],json.dumps(result, ensure_ascii=False)))
            await db._db.commit(); await db.set_setting("panelix_last_sync", str(now)); await db.set_setting("panelix_last_sync_result", json.dumps(result, ensure_ascii=False)); return result
        except (PanelixError, Exception) as exc:
            log.exception("Panelix catalog sync failed")
            result = {"success": False, "total": 0, "new": 0, "updated": 0, "unavailable": 0, "errors": 1, "error": _humanize_error(exc)}
            try:
                await db._db.execute("INSERT INTO panelix_sync_log(started_at,finished_at,success,error_count,detail) VALUES(?,?,?,?,?)", (started,int(time.time()),0,1,json.dumps(result, ensure_ascii=False))); await db._db.commit()
            except Exception: log.exception("could not write sync log")
            return result


async def get_catalog_by_subcategory(platform: str, subcategory: str):
    async with db._db.execute("SELECT * FROM sintel_services WHERE provider='panelix' AND platform=? AND subcategory=? AND is_active=1 AND price_verified=1 ORDER BY display_order,name", (platform,subcategory)) as cur: return [dict(r) for r in await cur.fetchall()]

async def get_cached_catalog(platform: str | None = None):
    sql = "SELECT * FROM sintel_services WHERE provider='panelix' AND is_active=1" + (" AND platform=?" if platform else "") + " ORDER BY platform,subcategory,display_order,name"
    async with db._db.execute(sql, (platform,) if platform else ()) as cur: return [dict(r) for r in await cur.fetchall()]

async def get_service_by_id(service_id: int):
    async with db._db.execute("SELECT * FROM sintel_services WHERE provider='panelix' AND service_id=? AND is_active=1 AND price_verified=1", (int(service_id),)) as cur:
        row = await cur.fetchone(); return dict(row) if row else None
