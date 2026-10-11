"""SimPars - اتصال به درگاه زرین‌پال (API v4)."""
from __future__ import annotations

import asyncio
import aiohttp

REQUEST_URL = "https://payment.zarinpal.com/pg/v4/payment/request.json"
VERIFY_URL = "https://payment.zarinpal.com/pg/v4/payment/verify.json"
START_URL = "https://www.zarinpal.com/pg/StartPay/{authority}"
TIMEOUT = aiohttp.ClientTimeout(total=25)

RESULT_MESSAGES = {
    -9: "خطای اعتبارسنجی درخواست",
    -10: "مرچنت زرین‌پال نامعتبر است",
    -11: "مرچنت فعال نیست",
    -12: "مبلغ تراکنش نامعتبر است",
    -14: "آدرس بازگشت نامعتبر است",
    -33: "مبلغ تراکنش با مبلغ اصلی برابر نیست",
    -40: "خطا در اطلاعات اضافی تراکنش",
    -41: "اطلاعات اضافی تراکنش نامعتبر است",
    -54: "درخواست تکراری یا تراکنش منقضی است",
}

class ZarinpalError(Exception):
    pass

async def _post(url: str, payload: dict) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.post(url, json=payload, headers={"Accept": "application/json", "Content-Type": "application/json"}) as resp:
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        raise ZarinpalError("خطا در اتصال به درگاه زرین‌پال") from exc
    if not isinstance(data, dict):
        raise ZarinpalError("پاسخ نامعتبر از درگاه زرین‌پال")
    return data

def _data(data: dict) -> dict:
    value = data.get("data")
    return value if isinstance(value, dict) else {}

def _code(data: dict):
    return _data(data).get("code", data.get("code"))

async def create_payment(merchant: str, amount_rial: int, callback_url: str, description: str = "", order_id: str | None = None) -> str:
    payload = {"merchant_id": merchant, "amount": int(amount_rial), "currency": "IRR", "description": description, "callback_url": callback_url}
    if order_id:
        payload["metadata"] = {"order_id": str(order_id)}
    response = await _post(REQUEST_URL, payload)
    if _code(response) == 100 and _data(response).get("authority"):
        return str(_data(response)["authority"])
    code = _code(response)
    raise ZarinpalError(RESULT_MESSAGES.get(code) or response.get("errors") or f"خطای {code}")

async def verify_payment(merchant: str, authority: str, amount_rial: int) -> dict:
    return await _post(VERIFY_URL, {"merchant_id": merchant, "amount": int(amount_rial), "authority": authority})

def payment_url(authority: str) -> str:
    return START_URL.format(authority=authority)
