"""نگهبان نرخ فروش دلار با وب‌سرویس رسمی نوسان."""
from __future__ import annotations

import os
import time
from typing import Any

import aiohttp

import database as db

# طبق راهنمای رسمی نوسان: /latest/?api_key=...&item=usd_sell
DEFAULT_URL = "https://api.navasan.tech/latest/"
MAX_RATE_AGE = 1800


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").replace("٬", "").strip())
        except ValueError:
            return None
    return None


def _extract_usd_sell(payload: Any) -> float | None:
    """Extract only usd_sell.value, never a random nested market field."""
    if not isinstance(payload, dict):
        return None
    item = payload.get("usd_sell")
    if isinstance(item, dict):
        for key in ("value", "price", "sell"):
            rate = _number(item.get(key))
            if rate and 1_000 < rate < 100_000_000:
                return rate
    rate = _number(item)
    if rate and 1_000 < rate < 100_000_000:
        return rate
    return None


async def fetch_usd_rate() -> float:
    api_key = (await db.get_setting("usd_rate_api_key") or os.getenv("USD_RATE_API_KEY", "")).strip()
    url = (await db.get_setting("usd_rate_url") or os.getenv("USD_RATE_URL", DEFAULT_URL)).strip()
    if not api_key:
        raise RuntimeError("کلید API نوسان ثبت نشده است")
    if "api.navasan.tech" in url and not url.endswith("/"):
        url += "/"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            async with session.get(
                url,
                params={"api_key": api_key, "item": "usd_sell"},
                headers={"Accept": "application/json"},
            ) as response:
                if response.status >= 400:
                    raise RuntimeError(f"Navasan HTTP {response.status}")
                payload = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"خطا در اتصال به نوسان: {exc}") from exc
    rate = _extract_usd_sell(payload)
    if not rate:
        raise RuntimeError("پاسخ نوسان شامل usd_sell معتبر نیست")
    return rate


async def refresh_rate() -> tuple[bool, str]:
    try:
        rate = await fetch_usd_rate()
        await db.set_setting("rate", f"{rate:g}")
        await db.set_setting("rate_source", "Navasan usd_sell")
        await db.set_setting("rate_updated_at", str(int(time.time())))
        await db.set_setting("pricing_paused", "0")
        return True, f"{rate:,.0f} تومان"
    except Exception as exc:
        source = await db.get_setting("rate_source")
        updated = await db.get_int("rate_updated_at", 0)
        if source == "Navasan usd_sell" and updated and time.time() - updated > MAX_RATE_AGE:
            await db.set_setting("pricing_paused", "1")
        return False, str(exc)


async def sales_allowed() -> bool:
    rate = await db.get_float("rate", 0)
    paused = await db.get_setting("pricing_paused") == "1"
    source = await db.get_setting("rate_source") or "manual fallback"
    if paused and source not in ("Navasan usd_sell",) and rate > 0:
        await db.set_setting("pricing_paused", "0")
        paused = False
    return not paused and rate > 0


async def snapshot() -> dict[str, str]:
    updated = await db.get_int("rate_updated_at", 0)
    age = int(time.time() - updated) if updated else None
    return {
        "rate": f"{await db.get_float('rate', 1200):,.0f}",
        "source": await db.get_setting("rate_source") or "manual fallback",
        "age": str(age) if age is not None else "unknown",
        "paused": await db.get_setting("pricing_paused") or "0",
    }
