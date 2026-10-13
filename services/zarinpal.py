"""SimPars - اتصال به درگاه زرین‌پال (API v4).

نکات مهم:
- لینک StartPay مستقیماً به کاربر تلگرام داده نمی‌شود؛ کاربر اول به
  ``{BASE_URL}/pay/<authority>`` روی دامنه خودمان می‌رود و از آنجا به درگاه
  هدایت می‌شود تا Referer برابر دامنه ثبت‌شده در زرین‌پال باشد.
- مرچنت سندباکس (همه صفر) به endpointهای sandbox ارسال می‌شود، نه production.
"""
from __future__ import annotations

import asyncio
import re

import aiohttp

from config import BASE_URL

SANDBOX_MERCHANT = "00000000-0000-0000-0000-000000000000"

REQUEST_URL = "https://payment.zarinpal.com/pg/v4/payment/request.json"
VERIFY_URL = "https://payment.zarinpal.com/pg/v4/payment/verify.json"
START_URL = "https://payment.zarinpal.com/pg/StartPay/{authority}"

SANDBOX_REQUEST_URL = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
SANDBOX_VERIFY_URL = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
SANDBOX_START_URL = "https://sandbox.zarinpal.com/pg/StartPay/{authority}"

AUTHORITY_RE = re.compile(r"^[A-Za-z0-9]{20,64}$")
TIMEOUT = aiohttp.ClientTimeout(total=25)
RESULT_MESSAGES = {
    -9: "خطای اعتبارسنجی درخواست (مرچنت/مبلغ/آدرس بازگشت را بررسی کن)",
    -10: "مرچنت زرین‌پال نامعتبر است",
    -11: "مرچنت فعال نیست",
    -12: "تلاش بیش از حد در یک بازه زمانی کوتاه",
    -15: "درگاه پرداخت به حالت تعلیق درآمده",
    -16: "سطح تایید پذیرنده پایین‌تر از سطح نقره‌ای است",
    -14: "آدرس بازگشت (Callback) با دامنه ثبت‌شده در زرین‌پال یکی نیست",
    -33: "مبلغ تراکنش با مبلغ اصلی برابر نیست",
    -40: "خطا در اطلاعات اضافی تراکنش",
    -41: "اطلاعات اضافی تراکنش نامعتبر است",
    -50: "مبلغ پرداخت‌شده با مبلغ وریفای متفاوت است",
    -51: "پرداخت ناموفق",
    -54: "درخواست تکراری یا تراکنش منقضی است",
}


class ZarinpalError(Exception):
    pass


def is_sandbox_merchant(merchant: str) -> bool:
    return (merchant or "").strip() == SANDBOX_MERCHANT


def valid_authority(authority: str) -> bool:
    return bool(AUTHORITY_RE.match(authority or ""))


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
    code = _data(data).get("code")
    if code is None:
        errors = data.get("errors")
        if isinstance(errors, dict):
            code = errors.get("code")
    return code if code is not None else data.get("code")


async def create_payment(merchant: str, amount_rial: int, callback_url: str, description: str = "", order_id: str | None = None) -> str:
    if not callback_url.lower().startswith("https://"):
        raise ZarinpalError("آدرس Callback باید کامل و با https:// باشد")
    payload = {
        "merchant_id": merchant,
        "amount": int(amount_rial),
        "currency": "IRR",
        "description": description or "SimPars payment",
        "callback_url": callback_url,
    }
    if order_id:
        payload["metadata"] = {"order_id": str(order_id)}
    url = SANDBOX_REQUEST_URL if is_sandbox_merchant(merchant) else REQUEST_URL
    response = await _post(url, payload)
    if _code(response) == 100 and _data(response).get("authority"):
        return str(_data(response)["authority"])
    code = _code(response)
    errors = response.get("errors")
    detail = errors.get("message") if isinstance(errors, dict) else errors
    raise ZarinpalError(RESULT_MESSAGES.get(code) or detail or f"خطای {code}")


async def verify_payment(merchant: str, authority: str, amount_rial: int) -> dict:
    url = SANDBOX_VERIFY_URL if is_sandbox_merchant(merchant) else VERIFY_URL
    return await _post(url, {"merchant_id": merchant, "amount": int(amount_rial), "authority": authority})


def gateway_url(authority: str, sandbox: bool = False) -> str:
    """آدرس مستقیم StartPay زرین‌پال (فقط در صفحه واسط سرور خودمان استفاده می‌شود)."""
    return (SANDBOX_START_URL if sandbox else START_URL).format(authority=authority)


def payment_url(authority: str, sandbox: bool = False) -> str:
    """لینکی که در فاکتور تلگرام نمایش داده می‌شود.

    اگر BASE_URL تنظیم شده باشد کاربر از دامنه خودمان وارد درگاه می‌شود
    تا Referer درست ارسال شود؛ در غیر این صورت لینک مستقیم برگردانده می‌شود.
    """
    if BASE_URL:
        return f"{BASE_URL}/pay/{authority}"
    return gateway_url(authority, sandbox)
