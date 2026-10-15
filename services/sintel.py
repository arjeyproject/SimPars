"""SINTELL SMM API v2 client (https://sintell.ir/blog/smm-api).

All requests: HTTP POST form fields `key` + `action` to https://sintell.ir/panel/api.php, JSON reply.
Errors come back as {"error": "..."}.
"""
from __future__ import annotations
import asyncio, json, logging, os, re, socket, time
from typing import Any
import aiohttp
from utils import mask

log = logging.getLogger(__name__)
API_BASE = os.getenv("SINTEL_API_URL", "https://sintell.ir/panel/api.php").strip() or "https://sintell.ir/panel/api.php"
SINTEL_PROXY = os.getenv("SINTEL_PROXY", "").strip() or None
FORCE_IPV4 = os.getenv("SINTEL_FORCE_IPV4", "1").strip() != "0"
_TIMEOUT = aiohttp.ClientTimeout(total=40, connect=15, sock_connect=15, sock_read=30)
_RETRIES = 2
CATALOG_CACHE_TTL = 300
_catalog_cache = None
_catalog_cache_time = 0.0
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SimParsBot/1.0",
}


class SintelError(Exception):
    pass


ERROR_MESSAGES = {
    "sintel_connect_timeout": "🌐 سرور ربات اصلاً به sintell.ir وصل نمی‌شود (مشکل شبکه/IP سرور، نه کلید). اگر VPS خارج از ایران است، SINTEL_PROXY را در .env تنظیم کن.",
    "sintel_read_timeout": "⏱ اتصال برقرار شد ولی سینتل پاسخ نداد (مشکل شبکه، نه کلید).",
    "sintel_network": "🌐 خطا در اتصال شبکه به sintell.ir.",
    "invalid key": "🔑 کلید API نامعتبر است.",
    "incorrect key": "🔑 کلید API نامعتبر است.",
    "key not found": "🔑 کلید API پیدا نشد.",
    "unauthorized": "🔑 دسترسی API رد شد.",
    "invalid service": "❌ سرویس نامعتبر است.",
    "invalid link": "❌ لینک نامعتبر است.",
    "invalid quantity": "❌ تعداد نامعتبر است.",
    "quantity must be": "❌ تعداد باید بین حداقل و حداکثر باشد.",
    "insufficient balance": "⚠️ موجودی پنل سینتل کافی نیست.",
    "not enough funds": "⚠️ موجودی پنل سینتل کافی نیست.",
    "rate limit": "⚠️ بیش از ۱۲۰ درخواست در دقیقه؛ کمی صبر کن.",
}
TELEGRAM_MARKERS = ("telegram", "تلگرام", "t.me", "channel", "کانال", "group", "گروه", "member", "subscriber", "reaction", "ریاکشن")
INSTAGRAM_MARKERS = ("instagram", "اینستا", "insta", "instagr.am", "reels", "ریلز", "story", "استوری", "فالوور", "followers")


def _humanize_error(error):
    raw = str(error).strip(); low = raw.lower()
    for key, msg in ERROR_MESSAGES.items():
        if key in low:
            return msg
    return f"⚠️ پاسخ سینتل: {raw[:220]}" if raw else "⚠️ پاسخ خالی از سینتل دریافت شد."


def clean_api_key(value: str) -> str:
    value = str(value or "").strip().replace("\u200c", "").replace("\u200f", "").replace("\u200e", "")
    value = re.sub(r"^```(?:text|plain)?\s*|\s*```$", "", value, flags=re.I).strip().strip(' "\'<>`')
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value.split()[0] if value.split() else ""


def _as_int(v, default=0):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def classify_service(s):
    explicit = str(s.get("platform") or s.get("network") or "").lower()
    text = " ".join(str(s.get(k, "")) for k in ("name", "category", "type", "description")).lower()
    if "insta" in explicit: return "instagram"
    if "telegram" in explicit: return "telegram"
    if any(x in text for x in INSTAGRAM_MARKERS): return "instagram"
    if any(x in text for x in TELEGRAM_MARKERS): return "telegram"
    return "other"


def normalize_service(raw):
    r = dict(raw)
    r["service"] = _as_int(raw.get("service", raw.get("id", 0)))
    r["min"] = _as_int(raw.get("min", 0)); r["max"] = _as_int(raw.get("max", 0))
    r["rate"] = str(raw.get("rate", "0"))
    r["name"] = str(raw.get("name", "سرویس نامشخص")).strip()
    r["_platform"] = classify_service(r)
    return r


def _provider_error(result):
    # Per docs, every failure is {"error": "..."}; nothing else is an error.
    if isinstance(result, dict) and result.get("error") not in (None, "", False):
        return str(result["error"])
    return ""


def _connector():
    return aiohttp.TCPConnector(family=socket.AF_INET if FORCE_IPV4 else 0, ttl_dns_cache=300)


async def _post_once(payload):
    async with aiohttp.ClientSession(timeout=_TIMEOUT, connector=_connector(), headers=_HEADERS) as session:
        async with session.post(API_BASE, data=payload, proxy=SINTEL_PROXY) as response:
            return response.status, await response.text()


async def _request(key, action, **params):
    key = clean_api_key(key)
    if not key:
        raise SintelError("invalid key")
    payload = {"key": key, "action": action, **{k: v for k, v in params.items() if v is not None}}
    last = None
    for attempt in range(_RETRIES + 1):
        try:
            status, body = await _post_once(payload)
            break
        except (aiohttp.ServerTimeoutError, asyncio.TimeoutError) as exc:
            text = str(exc).lower()
            last = SintelError("sintel_connect_timeout" if "connect" in text or not text else "sintel_read_timeout")
            log.warning("Sintel %s timeout (attempt %d): %r", action, attempt + 1, exc)
        except (aiohttp.ClientConnectorError, aiohttp.ClientOSError) as exc:
            last = SintelError(f"sintel_connect_timeout: {exc}")
            log.warning("Sintel %s connect error (attempt %d): %s", action, attempt + 1, exc)
        except aiohttp.ClientError as exc:
            last = SintelError(f"sintel_network: {exc}")
            log.warning("Sintel %s network error (attempt %d): %s", action, attempt + 1, exc)
        await asyncio.sleep(1.5 * (attempt + 1))
    else:
        raise last or SintelError("sintel_network")
    log.info("Sintel %s -> HTTP %s (%d bytes)", action, status, len(body))
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SintelError(f"پاسخ غیر JSON (HTTP {status}): {body[:150]}") from exc
    error = _provider_error(result)
    if error:
        raise SintelError(error)
    if status >= 400:
        raise SintelError(f"HTTP {status}")
    return result


class SintelClient:
    def __init__(self, api_key):
        self.api_key = clean_api_key(api_key)
        if not self.api_key:
            raise SintelError("invalid key")

    async def get_balance(self) -> float:
        result = await _request(self.api_key, "balance")
        if isinstance(result, dict) and result.get("balance") is not None:
            try:
                return float(str(result["balance"]).replace(",", ""))
            except ValueError:
                pass
        raise SintelError(f"پاسخ balance ناشناخته: {json.dumps(result, ensure_ascii=False)[:160]}")

    async def test_connection(self):
        return await _request(self.api_key, "balance")

    async def get_services(self, lang="fa", use_cache=True):
        global _catalog_cache, _catalog_cache_time
        now = time.time()
        if use_cache and _catalog_cache is not None and now - _catalog_cache_time < CATALOG_CACHE_TTL:
            return _catalog_cache
        result = await _request(self.api_key, "services", lang=lang)
        services = [normalize_service(x) for x in result if isinstance(x, dict)] if isinstance(result, list) else []
        _catalog_cache, _catalog_cache_time = services, now
        return services

    async def create_order(self, service_id, link, quantity):
        result = await _request(self.api_key, "add", service=int(service_id), link=link.strip(), quantity=int(quantity))
        if not isinstance(result, dict) or not result.get("order"):
            raise SintelError("شناسه سفارش برنگشت")
        return result

    async def find_orders_by_link(self, link, limit=5):
        return await _request(self.api_key, "orders", link=link.strip(), limit=int(limit))

    async def get_order_status(self, order_id):
        result = await _request(self.api_key, "status", order=int(order_id))
        if not isinstance(result, dict):
            raise SintelError("وضعیت سفارش پیدا نشد")
        return result

    async def cancel_order(self, order_id):
        return bool(await _request(self.api_key, "cancel", orders=str(int(order_id))))

    async def refill_order(self, order_id):
        return bool(await _request(self.api_key, "refill", order=int(order_id)))


def invalidate_catalog_cache():
    global _catalog_cache, _catalog_cache_time
    _catalog_cache = None; _catalog_cache_time = 0.0


def masked_key(key):
    return mask(key)
