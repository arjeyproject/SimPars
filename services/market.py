"""Live FX pricing guard for storefront safety.

The provider is optional and configurable. When it is unavailable the bot keeps
using the last admin-set rate, but pauses sales once that rate is too old.
"""
from __future__ import annotations

import os
import time
from typing import Any

import aiohttp

import database as db

DEFAULT_URL = "https://api.navasan.tech/latest/"
REFRESH_SECONDS = 300
MAX_RATE_AGE = 1800


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("٬", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _find_rate(payload: Any) -> float | None:
    """Accept common provider shapes without trusting arbitrary fields."""
    if isinstance(payload, dict):
        for key in ("usd_sell", "usd", "price", "value", "sell", "sell_price"):
            rate = _number(payload.get(key))
            if rate and 1_000 < rate < 100_000_000:
                return rate
        for value in payload.values():
            rate = _find_rate(value)
            if rate:
                return rate
    elif isinstance(payload, list):
        for value in payload:
            rate = _find_rate(value)
            if rate:
                return rate
    return None


async def fetch_usd_rate() -> float:
    api_key = (await db.get_setting("usd_rate_api_key") or os.getenv("USD_RATE_API_KEY", "")).strip()
    url = (await db.get_setting("usd_rate_url") or os.getenv("USD_RATE_URL", DEFAULT_URL)).strip()
    if not api_key and "navasan.tech" in url:
        raise RuntimeError("USD rate provider key is not configured")
    params = {"api_key": api_key} if api_key else None
    timeout = aiohttp.ClientTimeout(total=12)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params, headers={"Accept": "application/json"}) as response:
                if response.status >= 400:
                    raise RuntimeError(f"provider http {response.status}")
                payload = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        raise RuntimeError(str(exc)) from exc
    rate = _find_rate(payload)
    if not rate:
        raise RuntimeError("provider returned no valid USD sell rate")
    return rate


async def refresh_rate() -> tuple[bool, str]:
    """Refresh the store rate and set a fail-safe pause on stale live data."""
    try:
        rate = await fetch_usd_rate()
        await db.set_setting("rate", f"{rate:g}")
        await db.set_setting("rate_source", "live USD sell rate")
        await db.set_setting("rate_updated_at", str(int(time.time())))
        await db.set_setting("pricing_paused", "0")
        return True, f"{rate:,.0f}"
    except Exception as exc:  # provider failures must never crash the bot
        source = await db.get_setting("rate_source")
        updated = await db.get_int("rate_updated_at", 0)
        if source == "live USD sell rate" and updated and time.time() - updated > MAX_RATE_AGE:
            await db.set_setting("pricing_paused", "1")
        return False, str(exc)


async def sales_allowed() -> bool:
    return await db.get_setting("pricing_paused") != "1"


async def snapshot() -> dict[str, str]:
    updated = await db.get_int("rate_updated_at", 0)
    age = int(time.time() - updated) if updated else None
    return {
        "rate": f"{await db.get_float('rate', 1200):,.0f}",
        "source": await db.get_setting("rate_source") or "manual fallback",
        "age": str(age) if age is not None else "unknown",
        "paused": await db.get_setting("pricing_paused") or "0",
    }
