"""Sintel API Client - سرویس‌های SMM تلگرام و اینستاگرام."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from config import BASE_DIR
from utils import mask

log = logging.getLogger(__name__)

API_BASE = "https://sintell.ir/panel/api.php"
_TIMEOUT = aiohttp.ClientTimeout(total=60)

# Cache settings
CATALOG_CACHE_TTL = 300  # 5 minutes
_catalog_cache: dict[str, Any] | None = None
_catalog_cache_time: float = 0.0


class SintelError(Exception):
    """خطاهای API سینتل."""
    pass


# پیام‌های خطای سینتل
ERROR_MESSAGES = {
    "invalid key": "🔑 کلید API نامعتبر است.",
    "key not found": "🔑 کلید API پیدا نشد.",
    "invalid service": "❌ سرویس نامعتبر است.",
    "invalid link": "❌ لینک نامعتبر است.",
    "invalid quantity": "❌ تعداد نامعتبر است.",
    "quantity must be": "❌ تعداد باید بین حداقل و حداکثر باشد.",
    "insufficient balance": "⚠️ موجودی کیف پول سینتل کافی نیست.",
    "service unavailable": "❌ این سرویس فعلاً موجود نیست.",
    "rate limit": "⚠️ درخواست زیاد شده؛ کمی صبر کنید.",
}

# دسته‌بندی سرویس‌ها بر اساس نام
TELEGRAM_KEYWORDS = [
    "telegram", "تلگرام", "عضو", "member", "follow", "view", "بازدید",
    "like", "لایک", "comment", "کامنت", "reaction", "ریاکشن",
    "post", "پست", "channel", "کانال", "group", "گروه",
    "subscriber", "مشترک", "follower", " فالو",
]

INSTAGRAM_KEYWORDS = [
    "instagram", "اینستا", "ig", "insta",
    "followers", "فالوور", "following",
    "likes", "لایک", "views", "ویو", "بازدید",
    "comments", "کامنت", "reels", "ریلز",
    "story", "استوری", "save", "ذخیره",
    "impression", "ایمپرشن",
]


def _humanize_error(error: str | Exception) -> str:
    """تبدیل خطای سینتل به پیام فارسی."""
    text = str(error).lower()
    for key, message in ERROR_MESSAGES.items():
        if key in text:
            return message
    return "⚠️ خطا در ارتباط با سرویس سینتل."


def _classify_service(service_data: dict[str, Any]) -> str:
    """طبقه‌بندی سرویس به تلگرام یا اینستاگرام."""
    name = service_data.get("name", "").lower()
    category = service_data.get("category", "").lower()

    full_text = f"{name} {category}"

    # بررسی اینستاگرام
    for keyword in INSTAGRAM_KEYWORDS:
        if keyword in full_text:
            return "instagram"

    # بررسی تلگرام
    for keyword in TELEGRAM_KEYWORDS:
        if keyword in full_text:
            return "telegram"

    # پیش‌فرض تلگرام برای سرویس‌های نامشخص
    return "telegram"


def _mask_key(key: str) -> str:
    """ماسک کردن کلید API."""
    return mask(key)


async def _request(key: str, action: str, **params) -> dict[str, Any] | list[dict]:
    """
    ارسال درخواست به API سینتل.

    Args:
        key: کلید API
        action: اکشن مورد نظر
        **params: پارامترهای اضافی

    Returns:
        پاسخ JSON از API

    Raises:
        SintelError: در صورت خطا
    """
    data = {"key": key, "action": action, **params}

    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(API_BASE, data=data) as resp:
                status = resp.status
                text = await resp.text()
    except asyncio.TimeoutError:
        raise SintelError("timeout: سرور سینتل پاسخ نداد.")
    except aiohttp.ClientError as exc:
        raise SintelError(f"network error: {exc}")

    # لاگ کردن درخواست بدون افشای کلید
    log.debug("Sintel API request: action=%s, status=%s", action, status)

    # بررسی پاسخ
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise SintelError(f"پاسخ نامعتبر از سرور: {text[:200]}")

    # بررسی خطاها
    if isinstance(result, dict) and "error" in result:
        error_msg = str(result["error"])
        raise SintelError(error_msg)

    return result


class SintelClient:
    """
    کلاینت API سینتل.

    Usage:
        client = SintelClient("YOUR_API_KEY")
        balance = await client.get_balance()
        services = await client.get_services()
        order = await client.create_order(service_id=123, link="...", quantity=100)
        status = await client.get_order_status(order_id=456)
    """

    def __init__(self, api_key: str):
        """
        ایجاد کلاینت سینتل.

        Args:
            api_key: کلید API از پنل سینتل
        """
        self.api_key = api_key.strip()
        if not self.api_key:
            raise SintelError("کلید API نمی‌تواند خالی باشد.")

    async def test_connection(self) -> dict[str, Any]:
        """
        تست اتصال به API.

        Returns:
            اطلاعات موجودی و وضعیت
        """
        return await _request(self.api_key, "balance")

    async def get_balance(self) -> float:
        """
        دریافت موجودی کیف پول.

        Returns:
            موجودی به تومان
        """
        result = await _request(self.api_key, "balance")
        if isinstance(result, dict):
            balance = result.get("balance", 0)
            return float(balance) if balance else 0.0
        return 0.0

    async def get_services(self, lang: str = "fa", use_cache: bool = True) -> list[dict[str, Any]]:
        """
        دریافت لیست سرویس‌ها.

        Args:
            lang: زبان پاسخ (fa/en)
            use_cache: استفاده از کش

        Returns:
            لیست سرویس‌ها با جزئیات
        """
        global _catalog_cache, _catalog_cache_time
        import time

        now = time.time()
        if use_cache and _catalog_cache is not None:
            if now - _catalog_cache_time < CATALOG_CACHE_TTL:
                return _catalog_cache

        result = await _request(self.api_key, "services", lang=lang)

        if isinstance(result, list):
            services = result
            # افزودن دسته‌بندی خودکار
            for service in services:
                service["_platform"] = _classify_service(service)

            _catalog_cache = services
            _catalog_cache_time = now
            log.info("Sintel catalog cached: %d services", len(services))
            return services

        return []

    async def get_telegram_services(self, use_cache: bool = True) -> list[dict[str, Any]]:
        """دریافت فقط سرویس‌های تلگرام."""
        all_services = await self.get_services(use_cache=use_cache)
        return [s for s in all_services if s.get("_platform") == "telegram"]

    async def get_instagram_services(self, use_cache: bool = True) -> list[dict[str, Any]]:
        """دریافت فقط سرویس‌های اینستاگرام."""
        all_services = await self.get_services(use_cache=use_cache)
        return [s for s in all_services if s.get("_platform") == "instagram"]

    async def get_service_by_id(self, service_id: int) -> dict[str, Any] | None:
        """دریافت یک سرویس خاص با شناسه."""
        services = await self.get_services(use_cache=True)
        for service in services:
            if int(service.get("service", 0)) == int(service_id):
                return service
        return None

    async def create_order(
        self,
        service_id: int,
        link: str,
        quantity: int,
    ) -> dict[str, Any]:
        """
        ثبت سفارش جدید.

        Args:
            service_id: شناسه سرویس
            link: لینک یا شناسه هدف
            quantity: تعداد

        Returns:
            اطلاعات سفارش شامل order_id

        Raises:
            SintelError: در صورت خطا
        """
        result = await _request(
            self.api_key,
            "add",
            service=service_id,
            link=link,
            quantity=quantity,
        )

        if isinstance(result, dict):
            if "error" in result:
                raise SintelError(result["error"])

            # بررسی پاسخ موفق
            order_id = result.get("order")
            if not order_id:
                raise SintelError("شناسه سفارش برنگشت.")

            return result

        raise SintelError("پاسخ نامعتبر از سرور.")

    async def get_order_status(self, order_id: int) -> dict[str, Any]:
        """
        بررسی وضعیت یک سفارش.

        Args:
            order_id: شناسه سفارش

        Returns:
            اطلاعات وضعیت شامل status, remains
        """
        result = await _request(self.api_key, "status", order=order_id)

        if isinstance(result, dict):
            return result
        elif isinstance(result, list) and len(result) > 0:
            return result[0]

        raise SintelError("وضعیت سفارش پیدا نشد.")

    async def get_orders_status(self, order_ids: list[int]) -> list[dict[str, Any]]:
        """
        بررسی وضعیت چند سفارش.

        Args:
            order_ids: لیست شناسه‌های سفارش

        Returns:
            لیست وضعیت‌ها
        """
        if not order_ids:
            return []

        orders_str = ",".join(str(oid) for oid in order_ids[:100])
        result = await _request(self.api_key, "status", orders=orders_str)

        if isinstance(result, list):
            return result
        return []

    async def cancel_order(self, order_id: int) -> bool:
        """
        لغو یک سفارش.

        Args:
            order_id: شناسه سفارش

        Returns:
            True در صورت موفقیت
        """
        result = await _request(self.api_key, "cancel", orders=str(order_id))

        if isinstance(result, dict):
            if "error" in result:
                raise SintelError(result["error"])
            return True
        return False

    async def refill_order(self, order_id: int) -> bool:
        """
        درخواست ریفیل (پر کردن مجدد) برای سفارش.

        Args:
            order_id: شناسه سفارش

        Returns:
            True در صورت موفقیت
        """
        result = await _request(self.api_key, "refill", order=order_id)

        if isinstance(result, dict):
            if "error" in result:
                raise SintelError(result["error"])
            return True
        return False


def invalidate_catalog_cache() -> None:
    """پاک کردن کش کاتالوگ."""
    global _catalog_cache, _catalog_cache_time
    _catalog_cache = None
    _catalog_cache_time = 0.0
