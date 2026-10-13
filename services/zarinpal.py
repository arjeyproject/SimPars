"""SimPars - اتصال به درگاه زرین‌پال (API v4).

مطابق مستندات رسمی: https://www.zarinpal.com/docs/paymentGateway/connectToGateway.html
- request.json:  merchant_id, amount, currency, description, callback_url, metadata{order_id,...}
  پاسخ موفق: data.code == 100 و data.authority
- StartPay:      https://payment.zarinpal.com/pg/StartPay/<authority>
- Callback:      ?Authority=...&Status=OK|NOK  (فقط برای OK باید verify زده شود)
- verify.json:   merchant_id, amount (ریال), authority
  پاسخ: data.code == 100 (اولین تایید) یا 101 (قبلاً تایید شده)، ref_id، card_pan

همه مبالغ داخل برنامه «تومان» هستند؛ تبدیل به ریال فقط در همین ماژول (مرز API) انجام می‌شود.
لینک StartPay مستقیماً به کاربر تلگرام داده نمی‌شود؛ کاربر اول به ``{BASE_URL}/pay/<authority>``
روی دامنه خودمان می‌رود تا Referer برابر دامنه ثبت‌شده در زرین‌پال باشد.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

import aiohttp

import config

log = logging.getLogger(__name__)
SANDBOX_MERCHANT = "00000000-0000-0000-0000-000000000000"

REQUEST_URL = "https://payment.zarinpal.com/pg/v4/payment/request.json"
VERIFY_URL = "https://payment.zarinpal.com/pg/v4/payment/verify.json"
START_URL = "https://payment.zarinpal.com/pg/StartPay/{authority}"

SANDBOX_REQUEST_URL = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
SANDBOX_VERIFY_URL = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
SANDBOX_START_URL = "https://sandbox.zarinpal.com/pg/StartPay/{authority}"

CURRENCY = "IRR"
SUCCESS = 100
ALREADY_VERIFIED = 101
AUTHORITY_RE = re.compile(r"^[A-Za-z0-9]{20,64}$")
MERCHANT_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
RESULT_MESSAGES = {
    -9: "خطای اعتبارسنجی درخواست (مرچنت/مبلغ/آدرس بازگشت را بررسی کن)",
    -10: "مرچنت یا IP پذیرنده نامعتبر است",
    -11: "مرچنت فعال نیست",
    -12: "تلاش بیش از حد در یک بازه زمانی کوتاه",
    -14: "آدرس بازگشت (Callback) با دامنه ثبت‌شده در زرین‌پال یکی نیست",
    -15: "درگاه پرداخت به حالت تعلیق درآمده",
    -16: "سطح تایید پذیرنده پایین‌تر از سطح نقره‌ای است",
    -33: "مبلغ تراکنش با مبلغ اصلی برابر نیست",
    -40: "خطا در اطلاعات اضافی تراکنش",
    -41: "اطلاعات اضافی تراکنش نامعتبر است",
    -50: "مبلغ پرداخت‌شده با مبلغ وریفای متفاوت است",
    -51: "پرداخت ناموفق یا انجام‌نشده",
    -53: "این Authority متعلق به این مرچنت نیست",
    -54: "Authority نامعتبر یا منقضی است",
    -55: "تراکنش مورد نظر یافت نشد",
}


class ZarinpalError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class VerifyResult:
    code: int | None
    ref_id: str
    card_pan: str
    message: str

    @property
    def ok(self) -> bool:
        return self.code in (SUCCESS, ALREADY_VERIFIED)


def toman_to_rial(amount_toman: int) -> int:
    value = int(amount_toman)
    if value <= 0:
        raise ZarinpalError("مبلغ تراکنش نامعتبر است")
    return value * 10


def is_sandbox_merchant(merchant: str) -> bool:
    return (merchant or "").strip() == SANDBOX_MERCHANT


def valid_authority(authority: str) -> bool:
    return bool(AUTHORITY_RE.match(authority or ""))


def valid_merchant(merchant: str) -> bool:
    return bool(MERCHANT_RE.match((merchant or "").strip()))


async def _transport(url: str, payload: dict):
    timeout = aiohttp.ClientTimeout(total=max(5, int(config.ZARINPAL_TIMEOUT)))
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload, headers={"Accept": "application/json", "Content-Type": "application/json"}) as resp:
            return await resp.json(content_type=None)


async def _post(url: str, payload: dict) -> dict:
    try:
        data = await _transport(url, payload)
    except asyncio.TimeoutError as exc:
        raise ZarinpalError("پاسخی از درگاه زرین‌پال دریافت نشد (Timeout)") from exc
    except (aiohttp.ClientError, OSError, ValueError) as exc:
        raise ZarinpalError("خطا در اتصال به درگاه زرین‌پال") from exc
    if not isinstance(data, dict):
        raise ZarinpalError("پاسخ نامعتبر از درگاه زرین‌پال")
    return data


def _data(response: dict) -> dict:
    value = response.get("data")
    return value if isinstance(value, dict) else {}


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _code(response: dict) -> int | None:
    code = _data(response).get("code")
    if code is None:
        errors = response.get("errors")
        if isinstance(errors, dict):
            code = errors.get("code")
    return _int_or_none(code)


def _error_text(response: dict, code) -> str:
    errors = response.get("errors")
    detail = errors.get("message") if isinstance(errors, dict) else None
    return RESULT_MESSAGES.get(code) or (str(detail) if detail else "") or f"خطای درگاه ({code})"


async def create_payment(merchant: str, amount_toman: int, callback_url: str, description: str = "", order_id: str | None = None, sandbox: bool = False) -> str:
    """Open a gateway request; returns the authority. Raises ZarinpalError on any failure."""
    if not valid_merchant(merchant):
        raise ZarinpalError("مرچنت زرین‌پال تنظیم نشده یا نامعتبر است")
    if not (callback_url or "").lower().startswith("https://"):
        raise ZarinpalError("آدرس Callback باید کامل و با https:// باشد")
    payload = {
        "merchant_id": merchant.strip(),
        "amount": toman_to_rial(amount_toman),
        "currency": CURRENCY,
        "description": (description or "SimPars payment")[:250],
        "callback_url": callback_url,
    }
    if order_id:
        payload["metadata"] = {"order_id": str(order_id)}
    sandbox = sandbox or is_sandbox_merchant(merchant)
    response = await _post(SANDBOX_REQUEST_URL if sandbox else REQUEST_URL, payload)
    code = _code(response)
    authority = str(_data(response).get("authority") or "")
    if code == SUCCESS and valid_authority(authority):
        return authority
    log.warning("zarinpal request rejected: code=%s order=%s", code, order_id)
    raise ZarinpalError(_error_text(response, code), code)


async def verify_payment(merchant: str, authority: str, amount_toman: int, sandbox: bool = False) -> VerifyResult:
    """Server-side verify; the amount must come from our database, never from the request."""
    if not valid_authority(authority):
        raise ZarinpalError("Authority نامعتبر است", -54)
    sandbox = sandbox or is_sandbox_merchant(merchant)
    response = await _post(SANDBOX_VERIFY_URL if sandbox else VERIFY_URL, {"merchant_id": merchant.strip(), "amount": toman_to_rial(amount_toman), "authority": authority})
    code = _code(response)
    data = _data(response)
    ref_id = str(data.get("ref_id") or "") if code in (SUCCESS, ALREADY_VERIFIED) else ""
    if code == SUCCESS and not ref_id:
        # A "success" without a reference number is not a documented valid response.
        raise ZarinpalError("پاسخ تایید زرین‌پال ناقص است (ref_id ندارد)")
    message = "Verified" if code in (SUCCESS, ALREADY_VERIFIED) else _error_text(response, code)
    return VerifyResult(code=code, ref_id=ref_id, card_pan=str(data.get("card_pan") or ""), message=message)


def gateway_url(authority: str, sandbox: bool = False) -> str:
    """آدرس مستقیم StartPay زرین‌پال (فقط در صفحه واسط سرور خودمان استفاده می‌شود)."""
    return (SANDBOX_START_URL if sandbox else START_URL).format(authority=authority)


def payment_url(authority: str, sandbox: bool = False) -> str:
    """لینکی که در فاکتور تلگرام نمایش داده می‌شود."""
    if config.BASE_URL:
        return f"{config.BASE_URL}/pay/{authority}"
    return gateway_url(authority, sandbox)
