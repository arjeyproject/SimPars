"""SimPars - اتصال به درگاه زرین‌پال (Payment Gateway API v4).

مطابق مستندات رسمی: https://www.zarinpal.com/docs/paymentGateway/connectToGateway
- request.json  -> دریافت authority (code=100)
- StartPay      -> هدایت خریدار به درگاه
- callback      -> ?Authority=...&Status=OK|NOK  (فقط در OK باید verify شود)
- verify.json   -> code=100 (اولین تایید) یا 101 (قبلاً تایید شده)
- inquiry.json  -> فقط استعلام وضعیت (VERIFIED/PAID/IN_BANK/FAILED/REVERSED)؛
                   هرگز به‌جای verify برای تایید پرداخت استفاده نمی‌شود.
- unVerified.json -> فهرست تراکنش‌های پرداخت‌شده‌ای که هنوز verify نشده‌اند.

لینک StartPay مستقیماً به کاربر تلگرام داده نمی‌شود؛ کاربر اول به
``{BASE_URL}/pay/<authority>`` روی دامنه خودمان می‌رود تا Referer برابر دامنه
ثبت‌شده باشد (جلوگیری از خطای -18).
"""
from __future__ import annotations

import asyncio
import logging
import re

import aiohttp

from config import BASE_URL

log = logging.getLogger(__name__)

SANDBOX_MERCHANT = "00000000-0000-0000-0000-000000000000"

_PROD = "https://payment.zarinpal.com/pg"
_SANDBOX = "https://sandbox.zarinpal.com/pg"

REQUEST_URL = f"{_PROD}/v4/payment/request.json"
VERIFY_URL = f"{_PROD}/v4/payment/verify.json"
INQUIRY_URL = f"{_PROD}/v4/payment/inquiry.json"
UNVERIFIED_URL = f"{_PROD}/v4/payment/unVerified.json"
START_URL = f"{_PROD}/StartPay/{{authority}}"

SANDBOX_REQUEST_URL = f"{_SANDBOX}/v4/payment/request.json"
SANDBOX_VERIFY_URL = f"{_SANDBOX}/v4/payment/verify.json"
SANDBOX_INQUIRY_URL = f"{_SANDBOX}/v4/payment/inquiry.json"
SANDBOX_UNVERIFIED_URL = f"{_SANDBOX}/v4/payment/unVerified.json"
SANDBOX_START_URL = f"{_SANDBOX}/StartPay/{{authority}}"

MERCHANT_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
AUTHORITY_RE = re.compile(r"^[A-Za-z0-9]{20,64}$")
MOBILE_RE = re.compile(r"^09\d{9}$")
TIMEOUT = aiohttp.ClientTimeout(total=25)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "SimParsBot/2.0"}
MAX_AMOUNT_RIAL = 1_000_000_000  # سقف ۱۰۰ میلیون تومان (خطای -41)
MAX_DESCRIPTION = 500             # سقف توضیحات (خطای -9)

SUCCESS = 100
ALREADY_VERIFIED = 101

# لیست رسمی خطاها: https://www.zarinpal.com/docs/paymentGateway/errorList
RESULT_MESSAGES = {
    -9: "خطای اعتبارسنجی (مرچنت، مبلغ، توضیحات یا آدرس بازگشت نامعتبر است)",
    -10: "مرچنت کد یا IP سرور برای این درگاه معتبر نیست",
    -11: "مرچنت کد فعال نیست؛ با پشتیبانی زرین‌پال تماس بگیر",
    -12: "تلاش بیش از حد مجاز در زمان کوتاه؛ چند دقیقه بعد دوباره امتحان کن",
    -13: "سقف تراکنش درگاه پر شده؛ مدارک پذیرنده را تکمیل کن",
    -14: "دامنه آدرس بازگشت (Callback) با دامنه ثبت‌شده درگاه یکی نیست",
    -15: "درگاه پرداخت تعلیق شده است",
    -16: "سطح تایید پذیرنده پایین‌تر از نقره‌ای است",
    -17: "محدودیت پذیرنده در سطح آبی",
    -18: "Referer با دامنه ثبت‌شده درگاه یکی نیست (لینک را از صفحه واسط سایت باز کن)",
    -19: "ایجاد تراکنش برای این ترمینال مسدود است",
    -40: "پارامتر expire_in نامعتبر است",
    -41: "حداکثر مبلغ پرداخت ۱۰۰ میلیون تومان است",
    -50: "مبلغ پرداخت‌شده با مبلغ وریفای متفاوت است",
    -51: "پرداخت ناموفق یا لغو شده است",
    -52: "خطای غیرمنتظره زرین‌پال؛ با پشتیبانی زرین‌پال تماس بگیر",
    -53: "این تراکنش متعلق به این مرچنت کد نیست",
    -54: "اتوریتی نامعتبر است",
    -55: "تراکنش مورد نظر یافت نشد",
}


class ZarinpalError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def is_sandbox_merchant(merchant: str) -> bool:
    return (merchant or "").strip() == SANDBOX_MERCHANT


def valid_merchant(merchant: str) -> bool:
    return bool(MERCHANT_RE.match((merchant or "").strip()))


def valid_authority(authority: str) -> bool:
    return bool(AUTHORITY_RE.match(authority or ""))


def normalize_mobile(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    return digits if MOBILE_RE.match(digits) else None


def _urls(merchant: str) -> dict:
    if is_sandbox_merchant(merchant):
        return {"request": SANDBOX_REQUEST_URL, "verify": SANDBOX_VERIFY_URL, "inquiry": SANDBOX_INQUIRY_URL, "unverified": SANDBOX_UNVERIFIED_URL}
    return {"request": REQUEST_URL, "verify": VERIFY_URL, "inquiry": INQUIRY_URL, "unverified": UNVERIFIED_URL}


async def _post(url: str, payload: dict) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.post(url, json=payload, headers=HEADERS) as resp:
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        raise ZarinpalError("خطا در اتصال به درگاه زرین‌پال") from exc
    if not isinstance(data, dict):
        raise ZarinpalError("پاسخ نامعتبر از درگاه زرین‌پال")
    return data


def _data(response: dict) -> dict:
    value = response.get("data")
    return value if isinstance(value, dict) else {}


def response_code(response: dict) -> int | None:
    """کد نتیجه؛ در موفقیت داخل data و در خطا داخل errors قرار دارد."""
    code = _data(response).get("code")
    if code is None:
        errors = response.get("errors")
        if isinstance(errors, dict):
            code = errors.get("code")
        elif isinstance(errors, list) and errors and isinstance(errors[0], dict):
            code = errors[0].get("code")
    if code is None:
        code = response.get("code")
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


def _error_from(response: dict) -> ZarinpalError:
    code = response_code(response)
    errors = response.get("errors")
    detail = ""
    if isinstance(errors, dict):
        detail = str(errors.get("message") or "")
        validations = errors.get("validations")
        if validations:
            detail = f"{detail} {validations}".strip()
    log.warning("ZarinPal error %s: %s", code, detail or response)
    return ZarinpalError(RESULT_MESSAGES.get(code) or detail or f"خطای {code}", code)


def message_for(code: int | None) -> str:
    return RESULT_MESSAGES.get(code) or f"خطای {code}"


async def create_payment(merchant: str, amount_rial: int, callback_url: str, description: str = "",
                         order_id: str | None = None, mobile: str | None = None, email: str | None = None) -> str:
    merchant = (merchant or "").strip()
    if not valid_merchant(merchant):
        raise ZarinpalError("مرچنت کد زرین‌پال نامعتبر است (باید ۳۶ کاراکتر به شکل xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx باشد)")
    if not (callback_url or "").lower().startswith("https://"):
        raise ZarinpalError("آدرس Callback باید کامل و با https:// باشد (BASE_URL را در .env تنظیم کن)")
    amount_rial = int(amount_rial)
    if amount_rial <= 0 or amount_rial > MAX_AMOUNT_RIAL:
        raise ZarinpalError(RESULT_MESSAGES[-41] if amount_rial > 0 else "مبلغ نامعتبر است")
    payload = {
        "merchant_id": merchant,
        "amount": amount_rial,
        "currency": "IRR",
        "description": (description or "SimPars payment")[:MAX_DESCRIPTION],
        "callback_url": callback_url,
    }
    metadata = {}
    if order_id:
        metadata["order_id"] = str(order_id)
    mobile = normalize_mobile(mobile)
    if mobile:
        metadata["mobile"] = mobile
    if email:
        metadata["email"] = str(email)
    if metadata:
        payload["metadata"] = metadata
    response = await _post(_urls(merchant)["request"], payload)
    authority = _data(response).get("authority")
    if response_code(response) == SUCCESS and authority:
        return str(authority)
    raise _error_from(response)


async def verify_payment(merchant: str, authority: str, amount_rial: int) -> dict:
    """پاسخ خام verify؛ code=100 یا 101 یعنی پرداخت موفق است."""
    merchant = (merchant or "").strip()
    return await _post(_urls(merchant)["verify"], {"merchant_id": merchant, "amount": int(amount_rial), "authority": authority})


async def inquiry_status(merchant: str, authority: str) -> str | None:
    """وضعیت تراکنش (VERIFIED, PAID, IN_BANK, FAILED, REVERSED) یا None اگر در دسترس نبود."""
    merchant = (merchant or "").strip()
    try:
        response = await _post(_urls(merchant)["inquiry"], {"merchant_id": merchant, "authority": authority})
    except ZarinpalError:
        return None
    status = _data(response).get("status")
    return str(status).upper() if status else None


async def unverified_authorities(merchant: str) -> list[str]:
    """تراکنش‌های پرداخت‌شده‌ای که هنوز verify نشده‌اند (برای بازیابی خودکار)."""
    merchant = (merchant or "").strip()
    try:
        response = await _post(_urls(merchant)["unverified"], {"merchant_id": merchant})
    except ZarinpalError:
        return []
    items = _data(response).get("authorities") or []
    result = []
    for item in items if isinstance(items, list) else []:
        authority = item.get("authority") if isinstance(item, dict) else item
        if authority and valid_authority(str(authority)):
            result.append(str(authority))
    return result


def gateway_url(authority: str, sandbox: bool = False) -> str:
    """آدرس مستقیم StartPay زرین‌پال (فقط در صفحه واسط سرور خودمان استفاده می‌شود)."""
    return (SANDBOX_START_URL if sandbox else START_URL).format(authority=authority)


def payment_url(authority: str, sandbox: bool = False) -> str:
    """لینکی که در فاکتور تلگرام نمایش داده می‌شود (از دامنه خودمان)."""
    if BASE_URL:
        return f"{BASE_URL}/pay/{authority}"
    return gateway_url(authority, sandbox)
