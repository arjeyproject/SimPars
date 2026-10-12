"""Live FX pricing guard with safe manual fallback."""
from __future__ import annotations
import os
import time
from typing import Any
import aiohttp
import database as db
DEFAULT_URL = "https://api.navasan.tech/latest/"
MAX_RATE_AGE = 1800


def _number(value: Any) -> float | None:
    if isinstance(value, bool): return None
    if isinstance(value, (int, float)): return float(value)
    if isinstance(value, str):
        try: return float(value.replace(",", "").replace("٬", "").strip())
        except ValueError: return None
    return None


def _find_rate(payload: Any) -> float | None:
    if isinstance(payload, dict):
        for key in ("usd_sell", "usd", "price", "value", "sell", "sell_price"):
            rate = _number(payload.get(key))
            if rate and 1_000 < rate < 100_000_000: return rate
        for value in payload.values():
            rate = _find_rate(value)
            if rate: return rate
    elif isinstance(payload, list):
        for value in payload:
            rate = _find_rate(value)
            if rate: return rate
    return None


async def fetch_usd_rate() -> float:
    api_key = (await db.get_setting("usd_rate_api_key") or os.getenv("USD_RATE_API_KEY", "")).strip()
    url = (await db.get_setting("usd_rate_url") or os.getenv("USD_RATE_URL", DEFAULT_URL)).strip()
    if not api_key and "navasan.tech" in url: raise RuntimeError("USD rate provider key is not configured")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            async with session.get(url, params={"api_key": api_key} if api_key else None, headers={"Accept":"application/json"}) as response:
                if response.status >= 400: raise RuntimeError(f"provider http {response.status}")
                rate = _find_rate(await response.json(content_type=None))
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        raise RuntimeError(str(exc)) from exc
    if not rate: raise RuntimeError("provider returned no valid USD sell rate")
    return rate


async def refresh_rate() -> tuple[bool, str]:
    try:
        rate = await fetch_usd_rate()
        await db.set_setting("rate", f"{rate:g}"); await db.set_setting("rate_source", "live USD sell rate"); await db.set_setting("rate_updated_at", str(int(time.time()))); await db.set_setting("pricing_paused", "0")
        return True, f"{rate:,.0f}"
    except Exception as exc:
        # A manually configured rate is valid. Never disable the store merely because optional FX API is absent.
        if await db.get_setting("rate_source") == "live USD sell rate":
            updated = await db.get_int("rate_updated_at", 0)
            if updated and time.time() - updated > MAX_RATE_AGE: await db.set_setting("pricing_paused", "1")
        return False, str(exc)


async def sales_allowed() -> bool:
    if await db.get_setting("pricing_paused") == "1":
        return False
    return await db.get_float("rate", 0) > 0


async def snapshot() -> dict[str, str]:
    updated = await db.get_int("rate_updated_at", 0)
    age = int(time.time() - updated) if updated else None
    return {"rate": f"{await db.get_float('rate', 1200):,.0f}", "source": await db.get_setting("rate_source") or "manual fallback", "age": str(age) if age is not None else "unknown", "paused": await db.get_setting("pricing_paused") or "0"}
