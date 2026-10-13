"""Coupon storage and validation backed by the existing settings table."""
from __future__ import annotations

import json
import time

import database as db


async def _read() -> dict:
    raw = await db.get_setting("coupons_json")
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


async def _write(value: dict) -> None:
    await db.set_setting("coupons_json", json.dumps(value, ensure_ascii=False, separators=(",", ":")))


async def list_coupons() -> dict:
    return await _read()


async def create_coupon(code: str, percent: int, max_uses: int = 0, expires_at: int = 0) -> None:
    code = code.strip().upper()
    if not code or not 1 <= int(percent) <= 100:
        raise ValueError("code or percent is invalid")
    coupons = await _read()
    coupons[code] = {"percent": int(percent), "max_uses": max(0, int(max_uses)), "uses": 0, "expires_at": max(0, int(expires_at))}
    await _write(coupons)


async def delete_coupon(code: str) -> bool:
    coupons = await _read()
    removed = coupons.pop(code.strip().upper(), None) is not None
    if removed:
        await _write(coupons)
    return removed


async def validate(code: str) -> tuple[bool, str, int]:
    code = code.strip().upper()
    coupons = await _read()
    item = coupons.get(code)
    if not item:
        return False, "کد تخفیف معتبر نیست.", 0
    if item.get("expires_at", 0) and int(item["expires_at"]) < int(time.time()):
        return False, "کد تخفیف منقضی شده است.", 0
    if item.get("max_uses", 0) and item.get("uses", 0) >= item["max_uses"]:
        return False, "ظرفیت استفاده از این کد تکمیل شده است.", 0
    return True, f"کد تخفیف {item['percent']}٪ اعمال شد.", int(item["percent"])


async def consume(code: str) -> None:
    coupons = await _read()
    item = coupons.get(code.strip().upper())
    if not item:
        return
    item["uses"] = int(item.get("uses", 0)) + 1
    await _write(coupons)
