"""SimPars - اتصال به API سایت 5sim.net"""
from __future__ import annotations

import asyncio
import json
import time

import aiohttp

API_BASE = "https://5sim.net/v1"
_TIMEOUT = aiohttp.ClientTimeout(total=25)
PRICE_CACHE_TTL = 60
COUNTRY_CACHE_TTL = 6 * 3600

_price_cache: dict[str, tuple[float, dict]] = {}
_country_cache: dict = {"time": 0.0, "data": {}}


class FiveSimError(Exception):
    pass


ERROR_MESSAGES = {
    "unauthorized": "🔑 API پنل 5Sim نامعتبر است یا ثبت نشده.",
    "no free phones": "😕 در حال حاضر شماره‌ای برای این کشور موجود نیست. کشور دیگری را امتحان کن.",
    "not enough user balance": "⚠️ موجودی تامین‌کننده موقتاً کافی نیست. لطفاً کمی بعد تلاش کن یا به پشتیبانی پیام بده.",
    "not enough rating": "⚠️ امکان خرید موقتاً وجود ندارد. لطفاً به پشتیبانی اطلاع بده.",
    "no product": "❌ این سرویس برای این کشور موجود نیست.",
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
    for key, text in ERROR_MESSAGES.items():
        if key in message:
            return text
    return "⚠️ خطا در ارتباط با سرور تامین‌کننده. لطفاً دوباره تلاش کن."


async def _request(path: str, token: str | None = None, params: dict | None = None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(API_BASE + path, headers=headers, params=params) as resp:
                status = resp.status
                text = await resp.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise FiveSimError(f"network error: {exc}") from exc
    if status == 401:
        raise FiveSimError("unauthorized")
    try:
        data = json.loads(text)
    except ValueError:
        raise FiveSimError(text.strip() or f"http {status}")
    if status >= 400:
        raise FiveSimError(text.strip() or f"http {status}")
    return data


async def get_product_prices(product: str, use_cache: bool = True) -> dict[str, tuple[str, float, int]]:
    """{country: (operator, cost, count)} - ارزان‌ترین اپراتور موجود هر کشور"""
    now = time.time()
    cached = _price_cache.get(product)
    if use_cache and cached and now - cached[0] < PRICE_CACHE_TTL:
        return cached[1]
    data = await _request("/guest/prices", params={"product": product})
    if isinstance(data, dict) and product in data and isinstance(data[product], dict):
        data = data[product]
    result: dict[str, tuple[str, float, int]] = {}
    if isinstance(data, dict):
        for country, operators in data.items():
            if not isinstance(operators, dict):
                continue
            best = None
            for operator, info in operators.items():
                if not isinstance(info, dict):
                    continue
                count = int(info.get("count") or 0)
                cost = info.get("cost")
                if count <= 0 or cost is None:
                    continue
                cost = float(cost)
                if best is None or cost < best[1]:
                    best = (operator, cost, count)
            if best:
                result[country] = best
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

    async def profile(self) -> dict:
        return await _request("/user/profile", self.token)

    async def buy(self, country: str, operator: str, product: str) -> dict:
        data = await _request(f"/user/buy/activation/{country}/{operator}/{product}", self.token)
        if not isinstance(data, dict) or "id" not in data or not data.get("phone"):
            raise FiveSimError(str(data))
        return data

    async def check(self, order_id: int) -> dict:
        data = await _request(f"/user/check/{order_id}", self.token)
        if not isinstance(data, dict):
            raise FiveSimError(str(data))
        return data

    async def cancel(self, order_id: int) -> dict:
        return await _request(f"/user/cancel/{order_id}", self.token)

    async def finish(self, order_id: int) -> dict:
        return await _request(f"/user/finish/{order_id}", self.token)

    async def ban(self, order_id: int) -> dict:
        return await _request(f"/user/ban/{order_id}", self.token)
