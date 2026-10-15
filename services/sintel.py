"""SINTELL SMM API client for Telegram and Instagram services."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp

from utils import mask

log = logging.getLogger(__name__)
API_BASE = "https://sintell.ir/panel/api.php"
_TIMEOUT = aiohttp.ClientTimeout(total=60)
CATALOG_CACHE_TTL = 300
_catalog_cache: list[dict[str, Any]] | None = None
_catalog_cache_time = 0.0


class SintelError(Exception):
    pass


ERROR_MESSAGES = {
    "invalid key": "🔑 کلید API نامعتبر است.",
    "key not found": "🔑 کلید API پیدا نشد.",
    "invalid service": "❌ سرویس نامعتبر است.",
    "invalid link": "❌ لینک نامعتبر است.",
    "invalid quantity": "❌ تعداد نامعتبر است.",
    "quantity must be": "❌ تعداد باید بین حداقل و حداکثر باشد.",
    "insufficient balance": "⚠️ موجودی پنل سینتل کافی نیست.",
    "service unavailable": "❌ این سرویس فعلاً موجود نیست.",
    "rate limit": "⚠️ درخواست زیاد شده؛ کمی صبر کنید.",
    "not enough funds": "⚠️ موجودی پنل سینتل کافی نیست.",
}


TELEGRAM_MARKERS = ("telegram", "تلگرام", "t.me", "channel", "کانال", "group", "گروه", "member", "subscriber", "reaction", "ریاکشن")
INSTAGRAM_MARKERS = ("instagram", "اینستا", "insta", "instagr.am", "reels", "ریلز", "story", "استوری", "فالوور", "followers")


def _humanize_error(error: str | Exception) -> str:
    text = str(error).lower()
    for key, message in ERROR_MESSAGES.items():
        if key in text:
            return message
    return "⚠️ خطا در ارتباط با سرویس سینتل."


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def classify_service(service: dict[str, Any]) -> str:
    """Classify using explicit provider metadata first, then conservative name markers."""
    explicit = str(service.get("platform") or service.get("network") or service.get("social") or "").lower()
    text = " ".join(str(service.get(k, "")) for k in ("name", "category", "type", "description", "platform", "network")).lower()
    if "instagram" in explicit or "insta" in explicit:
        return "instagram"
    if "telegram" in explicit:
        return "telegram"
    if any(marker in text for marker in INSTAGRAM_MARKERS):
        return "instagram"
    if any(marker in text for marker in TELEGRAM_MARKERS):
        return "telegram"
    return "telegram"


def normalize_service(raw: dict[str, Any]) -> dict[str, Any]:
    service_id = raw.get("service", raw.get("service_id", raw.get("id", 0)))
    minimum = raw.get("min", raw.get("min_quantity", raw.get("minimum", 0)))
    maximum = raw.get("max", raw.get("max_quantity", raw.get("maximum", 0)))
    result = dict(raw)
    result["service"] = _as_int(service_id)
    result["min"] = _as_int(minimum)
    result["max"] = _as_int(maximum)
    result["rate"] = str(raw.get("rate", raw.get("price", "0")))
    result["name"] = str(raw.get("name", raw.get("service_name", "سرویس نامشخص"))).strip()
    result["_platform"] = classify_service(result)
    return result


async def _request(key: str, action: str, **params) -> dict[str, Any] | list[Any]:
    if not key or not key.strip():
        raise SintelError("invalid key")
    payload = {"key": key.strip(), "action": action, **params}
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(API_BASE, data=payload) as response:
                body = await response.text()
                if response.status >= 400:
                    raise SintelError(f"HTTP {response.status}: {body[:200]}")
    except asyncio.TimeoutError as exc:
        raise SintelError("timeout") from exc
    except aiohttp.ClientError as exc:
        raise SintelError(f"network error: {exc}") from exc
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SintelError("invalid JSON response") from exc
    if isinstance(result, dict):
        error = result.get("error") or result.get("message") if result.get("status") in ("error", False, 0) else result.get("error")
        if error:
            raise SintelError(str(error))
    return result


class SintelClient:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        if not self.api_key:
            raise SintelError("invalid key")

    async def get_balance(self) -> float:
        result = await _request(self.api_key, "balance")
        if isinstance(result, dict):
            return float(result.get("balance", result.get("funds", 0)) or 0)
        return 0.0

    async def test_connection(self) -> dict[str, Any]:
        result = await _request(self.api_key, "balance")
        return result if isinstance(result, dict) else {"balance": 0}

    async def get_services(self, lang: str = "fa", use_cache: bool = True) -> list[dict[str, Any]]:
        global _catalog_cache, _catalog_cache_time
        now = time.time()
        if use_cache and _catalog_cache is not None and now - _catalog_cache_time < CATALOG_CACHE_TTL:
            return _catalog_cache
        result = await _request(self.api_key, "services", lang=lang)
        if isinstance(result, dict):
            result = result.get("services", result.get("data", []))
        services = [normalize_service(item) for item in result if isinstance(item, dict)] if isinstance(result, list) else []
        _catalog_cache, _catalog_cache_time = services, now
        log.info("Sintel catalog cached: %d services", len(services))
        return services

    async def get_telegram_services(self, use_cache: bool = True):
        return [s for s in await self.get_services(use_cache=use_cache) if s["_platform"] == "telegram"]

    async def get_instagram_services(self, use_cache: bool = True):
        return [s for s in await self.get_services(use_cache=use_cache) if s["_platform"] == "instagram"]

    async def create_order(self, service_id: int, link: str, quantity: int) -> dict[str, Any]:
        result = await _request(self.api_key, "add", service=int(service_id), link=link.strip(), quantity=int(quantity))
        if not isinstance(result, dict) or not result.get("order"):
            raise SintelError("شناسه سفارش برنگشت")
        return result

    async def get_order_status(self, order_id: int) -> dict[str, Any]:
        result = await _request(self.api_key, "status", order=int(order_id))
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            raise SintelError("وضعیت سفارش پیدا نشد")
        return result

    async def cancel_order(self, order_id: int) -> bool:
        result = await _request(self.api_key, "cancel", orders=str(int(order_id)))
        return isinstance(result, dict) and not result.get("error")

    async def refill_order(self, order_id: int) -> bool:
        result = await _request(self.api_key, "refill", order=int(order_id))
        return isinstance(result, dict) and not result.get("error")


def invalidate_catalog_cache() -> None:
    global _catalog_cache, _catalog_cache_time
    _catalog_cache = None
    _catalog_cache_time = 0.0


def masked_key(key: str) -> str:
    return mask(key)
