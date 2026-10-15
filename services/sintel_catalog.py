"""مدیریت کاتالوگ سرویس‌های سینتل - ذخیره و دسته‌بندی."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import database as db
from services.sintel import SintelClient, SintelError, _humanize_error, invalidate_catalog_cache

log = logging.getLogger(__name__)

# دسته‌بندی‌های سرویس‌ها
SERVICE_CATEGORIES = {
    "telegram": {
        "emoji": "👥",
        "title": "سرویس‌های تلگرام",
        "subcategories": {
            "members": {
                "emoji": "👥",
                "title": "اعضای کانال و گروه",
                "keywords": ["member", "subscriber", "عضو", "مشترک", "follow"],
            },
            "views": {
                "emoji": "👁️",
                "title": "بازدید پست",
                "keywords": ["view", "بازدید", "impression"],
            },
            "reactions": {
                "emoji": "❤️",
                "title": "ریاکشن و احساس",
                "keywords": ["reaction", "ریاکشن", "emoji", "feeling", "لایک"],
            },
            "comments": {
                "emoji": "💬",
                "title": "کامنت و نظر",
                "keywords": ["comment", "کامنت", "opinion"],
            },
            "shares": {
                "emoji": "📤",
                "title": "اشتراک‌گذاری",
                "keywords": ["share", "اشتراک", "repost"],
            },
            "other": {
                "emoji": "📊",
                "title": "سایر سرویس‌ها",
                "keywords": [],
            },
        },
    },
    "instagram": {
        "emoji": "📸",
        "title": "سرویس‌های اینستاگرام",
        "subcategories": {
            "followers": {
                "emoji": "👥",
                "title": "فالوور",
                "keywords": ["followers", "فالوور", "follower", "مشترک"],
            },
            "likes": {
                "emoji": "❤️",
                "title": "لایک",
                "keywords": ["like", "لایک", "heart"],
            },
            "views": {
                "emoji": "👁️",
                "title": "بازدید",
                "keywords": ["view", "بازدید", "watch", "igtv", "reel"],
            },
            "comments": {
                "emoji": "💬",
                "title": "کامنت",
                "keywords": ["comment", "کامنت"],
            },
            "story": {
                "emoji": "📱",
                "title": "استوری",
                "keywords": ["story", "استوری"],
            },
            "other": {
                "emoji": "📊",
                "title": "سایر سرویس‌ها",
                "keywords": [],
            },
        },
    },
}


def _detect_subcategory(platform: str, service_name: str, category: str) -> str:
    """تشخیص زیرشاخه بر اساس نام سرویس."""
    if platform not in SERVICE_CATEGORIES:
        return "other"

    full_text = f"{service_name} {category}".lower()

    subcats = SERVICE_CATEGORIES[platform]["subcategories"]
    for subcat_key, subcat_info in subcats.items():
        if subcat_key == "other":
            continue
        for keyword in subcat_info["keywords"]:
            if keyword.lower() in full_text:
                return subcat_key

    return "other"


def _format_price(rate: str | float, quantity: int) -> int:
    """
    محاسبه قیمت بر اساس rate سینتل.

    فرمول سینتل: rate × quantity ÷ 1000
    """
    try:
        rate_decimal = Decimal(str(rate))
        quantity_decimal = Decimal(str(quantity))
        cost = (rate_decimal * quantity_decimal) / Decimal("1000")
        return int(cost.quantize(Decimal("1")))
    except (ValueError, TypeError, decimal.InvalidOperation):
        return 0


def _format_service_info(service: dict[str, Any]) -> dict[str, Any]:
    """فرمت‌دهی اطلاعات سرویس برای نمایش."""
    return {
        "service_id": int(service.get("service", 0)),
        "name": service.get("name", ""),
        "type": service.get("type", ""),
        "category": service.get("category", ""),
        "platform": service.get("_platform", "telegram"),
        "rate": service.get("rate", "0"),
        "min": int(service.get("min", 0)),
        "max": int(service.get("max", 0)),
        "refill": bool(service.get("refill", False)),
        "cancel": bool(service.get("cancel", False)),
        "dripfeed": bool(service.get("dripfeed", False)),
        "description": service.get("description", ""),
    }


async def sync_catalog_from_provider(api_key: str) -> dict[str, Any]:
    """
    همگام‌سازی کاتالوگ از سینتل به دیتابیس محلی.

    Args:
        api_key: کلید API سینتل

    Returns:
        نتیجه همگام‌سازی شامل تعداد سرویس‌ها
    """
    try:
        client = SintelClient(api_key)
        services = await client.get_services(use_cache=False)

        if not services:
            return {"success": False, "error": "کاتالوگ خالی است", "count": 0}

        telegram_count = 0
        instagram_count = 0
        unknown_count = 0

        # پردازش هر سرویس
        for service in services:
            formatted = _format_service_info(service)
            platform = formatted["platform"]
            subcategory = _detect_subcategory(
                platform,
                formatted["name"],
                formatted["category"]
            )

            # ذخیره در دیتابیس
            await _save_service_to_db(formatted, subcategory)

            if platform == "telegram":
                telegram_count += 1
            elif platform == "instagram":
                instagram_count += 1
            else:
                unknown_count += 1

        # پاک کردن کش
        invalidate_catalog_cache()

        log.info(
            "Sintel catalog synced: %d Telegram, %d Instagram, %d unknown",
            telegram_count, instagram_count, unknown_count
        )

        return {
            "success": True,
            "total": len(services),
            "telegram": telegram_count,
            "instagram": instagram_count,
            "unknown": unknown_count,
        }

    except SintelError as exc:
        log.error("Sintel catalog sync failed: %s", exc)
        return {"success": False, "error": _humanize_error(exc), "count": 0}
    except Exception as exc:
        log.exception("Unexpected error during catalog sync")
        return {"success": False, "error": str(exc), "count": 0}


async def _save_service_to_db(service: dict[str, Any], subcategory: str) -> None:
    """ذخیره یک سرویس در دیتابیس محلی."""
    try:
        import json
        service_id = service["service_id"]
        extra_data = json.dumps({
            "type": service["type"],
            "category": service["category"],
            "platform": service["platform"],
            "subcategory": subcategory,
            "refill": service["refill"],
            "cancel": service["cancel"],
            "dripfeed": service["dripfeed"],
            "description": service["description"],
        })

        # درج یا بروزرسانی
        await db._db.execute("""
            INSERT INTO sintel_services (
                service_id, name, rate, min_quantity, max_quantity,
                platform, subcategory, extra_data, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(service_id) DO UPDATE SET
                name = excluded.name,
                rate = excluded.rate,
                min_quantity = excluded.min_quantity,
                max_quantity = excluded.max_quantity,
                platform = excluded.platform,
                subcategory = excluded.subcategory,
                extra_data = excluded.extra_data,
                updated_at = excluded.updated_at
        """, (
            service_id,
            service["name"],
            service["rate"],
            service["min"],
            service["max"],
            service["platform"],
            subcategory,
            extra_data,
            int(datetime.now().timestamp()),
        ))
        await db._db.commit()
    except Exception as exc:
        log.warning("Failed to save service %d to DB: %s", service.get("service_id"), exc)


async def get_cached_catalog(platform: str | None = None) -> list[dict[str, Any]]:
    """
    دریافت کاتالوگ کش‌شده.

    Args:
        platform: فیلتر پلتفرم (telegram/instagram)

    Returns:
        لیست سرویس‌ها
    """
    async with db._db.execute(
        "SELECT * FROM sintel_services WHERE is_active=1 ORDER BY platform, subcategory, name"
    ) as cur:
        rows = await cur.fetchall()

    services = []
    for row in rows:
        service = dict(row)
        if platform and service.get("platform") != platform:
            continue
        services.append(service)

    return services


async def get_catalog_by_subcategory(
    platform: str,
    subcategory: str
) -> list[dict[str, Any]]:
    """دریافت سرویس‌های یک زیرشاخه خاص."""
    async with db._db.execute("""
        SELECT * FROM sintel_services
        WHERE platform=? AND subcategory=? AND is_active=1
        ORDER BY name
    """, (platform, subcategory)) as cur:
        return [dict(row) for row in await cur.fetchall()]


async def get_service_by_id(service_id: int) -> dict[str, Any] | None:
    """دریافت یک سرویس خاص."""
    async with db._db.execute(
        "SELECT * FROM sintel_services WHERE service_id=?", (service_id,)
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


def calculate_selling_price(provider_cost: int, profit_percent: float) -> int:
    """
    محاسبه قیمت فروش با اعمال سود.

    Args:
        provider_cost: هزینه تمام‌شده به تومان
        profit_percent: درصد سود

    Returns:
        قیمت فروش به تومان
    """
    profit = int(provider_cost * profit_percent / 100)
    return provider_cost + profit


# Import decimal for price calculation
import decimal
