"""Panelix provider client.

The module name is kept for database and import compatibility with existing
Sintel-era deployments. No legacy provider is used by the active integration.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import aiohttp

from utils import mask

log = logging.getLogger(__name__)
API_BASE = os.getenv("PANELIX_API_URL", "https://panelix.ir/web/api/v1").strip() or "https://panelix.ir/web/api/v1"
_TIMEOUT = aiohttp.ClientTimeout(total=35, connect=10, sock_connect=10, sock_read=25)
_RETRIES = 2
_HEADERS = {"Accept": "application/json", "User-Agent": "SimParsBot/1.0"}


class PanelixError(Exception):
    pass

# Compatibility alias for callers that still import SintelError.
SintelError = PanelixError
ERROR_MESSAGES = {
    "invalid key": "🔑 کلید API پنلیکس نامعتبر است.",
    "incorrect key": "🔑 کلید API پنلیکس نامعتبر است.",
    "unauthorized": "🔑 دسترسی API پنلیکس رد شد.",
    "invalid service": "❌ سرویس نامعتبر است.",
    "invalid link": "❌ لینک نامعتبر است.",
    "invalid quantity": "❌ تعداد نامعتبر است.",
    "not enough funds": "⚠️ موجودی پنلیکس کافی نیست.",
    "insufficient balance": "⚠️ موجودی پنلیکس کافی نیست.",
    "rate limit": "⚠️ سقف درخواست API پنلیکس پر شده است.",
    "timeout": "⏱ پنلیکس دیر پاسخ داد؛ وضعیت درخواست باید بررسی شود.",
    "network error": "🌐 خطا در اتصال به پنلیکس.",
}


def clean_api_key(value: str) -> str:
    value = str(value or "").strip().replace("\u200c", "")
    value = re.sub(r"^```(?:text|plain)?\s*|\s*```$", "", value, flags=re.I).strip(" \\\"'<>`")
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value.split()[0] if value.split() else ""


def _humanize_error(error: Any) -> str:
    raw = str(error or "").strip()
    low = raw.lower()
    for key, message in ERROR_MESSAGES.items():
        if key in low:
            return message
    return f"⚠️ پاسخ پنلیکس: {raw[:220]}" if raw else "⚠️ پاسخ خالی از پنلیکس دریافت شد."


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def normalize_service(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    sid = _as_int(raw.get("service", raw.get("id")))
    name = str(raw.get("name") or "").strip()
    minimum, maximum = _as_int(raw.get("min")), _as_int(raw.get("max"))
    rate = str(raw.get("rate") or "").strip()
    if sid <= 0 or not name or minimum <= 0 or maximum < minimum or not rate:
        return None
    return {
        "service": sid, "name": name, "category": str(raw.get("category") or "").strip(),
        "type": str(raw.get("type") or "").strip(), "rate": rate, "min": minimum, "max": maximum,
        "description": str(raw.get("desc", raw.get("description")) or "").strip(),
        "dripfeed": bool(raw.get("dripfeed", False)), "refill": bool(raw.get("refill", False)),
        "cancel": bool(raw.get("cancel", False)),
        "currency": str(raw.get("currency") or "").strip(),
        "rate_unit": str(raw.get("rate_unit", raw.get("unit")) or "").strip(),
    }


def _provider_error(result: Any) -> str:
    return str(result.get("error")) if isinstance(result, dict) and result.get("error") else ""


async def _post_once(payload: dict[str, Any]) -> tuple[int, str]:
    async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=_HEADERS) as session:
        async with session.post(API_BASE, data=payload) as response:
            return response.status, await response.text()


async def _request(key: str, action: str, **params: Any) -> Any:
    key = clean_api_key(key)
    if not key:
        raise PanelixError("invalid key")
    payload = {"key": key, "action": action, **{k: v for k, v in params.items() if v is not None}}
    # add is never retried: a timeout may have created a paid order already.
    attempts = 1 if action == "add" else _RETRIES + 1
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            status, body = await _post_once(payload)
            break
        except (aiohttp.ServerTimeoutError, asyncio.TimeoutError):
            last = PanelixError("timeout")
        except aiohttp.ClientError as exc:
            last = PanelixError(f"network error: {exc}")
        if attempt + 1 < attempts:
            await asyncio.sleep(1.5 * (attempt + 1))
    else:
        raise last or PanelixError("network error")
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise PanelixError(f"invalid JSON response: HTTP {status}") from exc
    error = _provider_error(result)
    if error:
        raise PanelixError(error)
    if status >= 400:
        raise PanelixError(f"HTTP {status}")
    return result


class PanelixClient:
    def __init__(self, api_key: str):
        self.api_key = clean_api_key(api_key)
        if not self.api_key:
            raise PanelixError("invalid key")

    async def get_balance(self) -> dict[str, Any]:
        result = await _request(self.api_key, "balance")
        if not isinstance(result, dict) or result.get("balance") is None:
            raise PanelixError("invalid balance response")
        return result

    async def test_connection(self) -> dict[str, Any]:
        return await self.get_balance()

    async def get_services(self) -> list[dict[str, Any]]:
        result = await _request(self.api_key, "services")
        if not isinstance(result, list):
            raise PanelixError("invalid services response")
        return [service for item in result if (service := normalize_service(item))]

    async def create_order(self, service_id: int, link: str, quantity: int, runs: int | None = None, interval: int | None = None) -> dict[str, Any]:
        result = await _request(self.api_key, "add", service=int(service_id), link=link.strip(), quantity=int(quantity), runs=runs, interval=interval)
        if not isinstance(result, dict) or not result.get("order"):
            raise PanelixError("order id missing")
        return result

    async def get_order_status(self, order_id: int) -> dict[str, Any]:
        result = await _request(self.api_key, "status", order=int(order_id))
        if not isinstance(result, dict):
            raise PanelixError("status missing")
        return result

    async def refill_order(self, order_id: int) -> dict[str, Any]:
        return await _request(self.api_key, "refill", order=int(order_id))

    async def refill_status(self, refill_id: int) -> dict[str, Any]:
        return await _request(self.api_key, "refill_status", refill=int(refill_id))

    async def cancel_orders(self, order_ids: list[int]) -> Any:
        if not order_ids or len(order_ids) > 100:
            raise PanelixError("cancel batch must contain 1 to 100 orders")
        return await _request(self.api_key, "cancel", orders=",".join(str(int(x)) for x in order_ids))

    async def cancel_order(self, order_id: int) -> Any:
        return await self.cancel_orders([order_id])


# Existing imports use these names; keeping aliases avoids a risky migration.
SintelClient = PanelixClient

def masked_key(key: str) -> str:
    return mask(key)

def invalidate_catalog_cache() -> None:
    return None
