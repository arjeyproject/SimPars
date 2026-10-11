"""5SIM API client and normalized live availability helpers."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import aiohttp

API_BASE = "https://5sim.net/v1"
_TIMEOUT = aiohttp.ClientTimeout(total=25)
PRICE_CACHE_TTL = 60
COUNTRY_CACHE_TTL = 6 * 3600
_price_cache: dict[str, tuple[float, dict]] = {}
_all_prices_cache: tuple[float, dict] | None = None
_country_cache: dict = {"time": 0.0, "data": {}}


class FiveSimError(Exception):
    pass

ERROR_MESSAGES = {
    "unauthorized": "🔑 API پنل 5Sim نامعتبر است یا ثبت نشده.",
    "no free phones": "😕 در حال حاضر شماره‌ای برای این کشور موجود نیست. کشور دیگری را امتحان کن.",
    "not enough user balance": "⚠️ موجودی تامین‌کننده موقتاً کافی نیست. لطفاً کمی بعد تلاش کن.",
    "not enough rating": "⚠️ امکان خرید موقتاً وجود ندارد. لطفاً به پشتیبانی اطلاع بده.",
    "no product": "❌ این سرویس در 5Sim موجود نیست.",
    "bad country": "❌ کشور نامعتبر است.",
    "bad operator": "❌ اپراتور نامعتبر است.",
    "server offline": "🔌 سرور تامین‌کننده موقتاً در دسترس نیست.",
    "order not found": "❌ سفارش در سرور پیدا نشد.",
    "order expired": "⌛️ مهلت این سفارش تمام شده است.",
    "order has sms": "📩 برای این شماره پیامک دریافت شده و قابل لغو نیست.",
    "network error": "🌐 خطا در اتصال به سرور. چند لحظه دیگر دوباره تلاش کن.",
}


def humanize(error: Exception | str) -> str:
    message = str(error).lower()
    return next((text for key, text in ERROR_MESSAGES.items() if key in message), "⚠️ خطا در ارتباط با سرور تامین‌کننده.")


async def _request(path: str, token: str | None = None, params: dict | None = None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(API_BASE + path, headers=headers, params=params) as resp:
                status, text = resp.status, await resp.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise FiveSimError(f"network error: {exc}") from exc
    if status == 401:
        raise FiveSimError("unauthorized")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise FiveSimError(text.strip() or f"http {status}") from exc
    if status >= 400:
        raise FiveSimError(text.strip() or f"http {status}")
    return data


def _normalize(payload: Any, product: str | None = None) -> dict[str, tuple[str, float, int]]:
    """Normalize 5SIM's product/country/operator response to cheapest operator."""
    if product and isinstance(payload, dict) and product in payload:
        payload = payload[product]
    result = {}
    if not isinstance(payload, dict):
        return result
    for country, operators in payload.items():
        if not isinstance(operators, dict):
            continue
        best = None
        for operator, info in operators.items():
            if not isinstance(info, dict):
                continue
            try:
                cost, count = float(info.get("cost")), int(info.get("count") or 0)
            except (TypeError, ValueError):
                continue
            if cost > 0 and count > 0 and (best is None or cost < best[1]):
                best = (str(operator), cost, count)
        if best:
            result[str(country)] = best
    return result


async def get_all_prices(use_cache: bool = True) -> dict[str, dict[str, tuple[str, float, int]]]:
    global _all_prices_cache
    now = time.time()
    if use_cache and _all_prices_cache and now - _all_prices_cache[0] < PRICE_CACHE_TTL:
        return _all_prices_cache[1]
    payload = await _request("/guest/prices")
    result = {}
    if isinstance(payload, dict):
        for product in payload:
            prices = _normalize(payload, str(product))
            if prices:
                result[str(product)] = prices
    _all_prices_cache = (now, result)
    return result


async def get_product_prices(product: str, use_cache: bool = True) -> dict[str, tuple[str, float, int]]:
    now = time.time()
    cached = _price_cache.get(product)
    if use_cache and cached and now - cached[0] < PRICE_CACHE_TTL:
        return cached[1]
    payload = await _request("/guest/prices", params={"product": product})
    result = _normalize(payload, product)
    _price_cache[product] = (now, result)
    return result


async def get_countries() -> dict:
    now = time.time()
    if _country_cache["data"] and now - _country_cache["time"] < COUNTRY_CACHE_TTL:
        return _country_cache["data"]
    data = await _request("/guest/countries")
    if isinstance(data, dict):
        _country_cache.update(time=now, data=data)
        return data
    return {}


async def countries_safe() -> dict:
    try:
        return await get_countries()
    except FiveSimError:
        return _country_cache["data"] or {}


class FiveSimClient:
    def __init__(self, token: str):
        if not token:
            raise FiveSimError("unauthorized")
        self.token = token

    async def profile(self) -> dict: return await _request("/user/profile", self.token)
    async def buy(self, country: str, operator: str, product: str) -> dict:
        data = await _request(f"/user/buy/activation/{country}/{operator}/{product}", self.token)
        if not isinstance(data, dict) or "id" not in data or not data.get("phone"):
            raise FiveSimError(str(data))
        return data
    async def check(self, order_id: int) -> dict: return await _request(f"/user/check/{order_id}", self.token)
    async def cancel(self, order_id: int) -> dict: return await _request(f"/user/cancel/{order_id}", self.token)
    async def finish(self, order_id: int) -> dict: return await _request(f"/user/finish/{order_id}", self.token)
    async def ban(self, order_id: int) -> dict: return await _request(f"/user/ban/{order_id}", self.token)
