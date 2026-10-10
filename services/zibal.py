"""SimPars - اتصال به درگاه پرداخت زیبال"""
from __future__ import annotations

import asyncio

import aiohttp

REQUEST_URL = "https://gateway.zibal.ir/v1/request"
VERIFY_URL = "https://gateway.zibal.ir/v1/verify"
START_URL = "https://gateway.zibal.ir/start/{track_id}"
SANDBOX_MERCHANT = "zibal"
_TIMEOUT = aiohttp.ClientTimeout(total=25)

RESULT_MESSAGES = {
    102: "مرچنت یافت نشد",
    103: "مرچنت غیرفعال است",
    104: "مرچنت نامعتبر است",
    105: "مبلغ باید بیشتر از ۱,۰۰۰ ریال باشد",
    106: "آدرس بازگشت (callbackUrl) نامعتبر است",
    113: "مبلغ تراکنش از سقف مجاز بیشتر است",
    201: "این تراکنش قبلاً تایید شده است",
    202: "پرداخت انجام نشده یا ناموفق بوده است",
    203: "کد پیگیری (trackId) نامعتبر است",
}


class ZibalError(Exception):
    pass


async def _post(url: str, payload: dict) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        raise ZibalError("خطا در اتصال به درگاه زیبال") from exc
    if not isinstance(data, dict):
        raise ZibalError("پاسخ نامعتبر از درگاه زیبال")
    return data


async def create_payment(merchant: str, amount_rial: int, callback_url: str,
                         description: str = "", order_id: str | None = None) -> str:
    payload = {
        "merchant": merchant,
        "amount": int(amount_rial),
        "callbackUrl": callback_url,
        "description": description,
    }
    if order_id:
        payload["orderId"] = order_id
    data = await _post(REQUEST_URL, payload)
    if data.get("result") == 100 and data.get("trackId"):
        return str(data["trackId"])
    code = data.get("result")
    raise ZibalError(RESULT_MESSAGES.get(code) or data.get("message") or f"خطای {code}")


async def verify_payment(merchant: str, track_id: str) -> dict:
    return await _post(VERIFY_URL, {"merchant": merchant, "trackId": int(track_id)})


def payment_url(track_id: str) -> str:
    return START_URL.format(track_id=track_id)
