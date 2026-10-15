"""SINTELL SMM API client for Telegram and Instagram services."""
from __future__ import annotations
import asyncio, json, logging, re, time
from typing import Any
import aiohttp
from utils import mask
log=logging.getLogger(__name__)
API_BASE="https://sintell.ir/panel/api.php"; _TIMEOUT=aiohttp.ClientTimeout(total=60); CATALOG_CACHE_TTL=300
_catalog_cache=None; _catalog_cache_time=0.0
class SintelError(Exception): pass
ERROR_MESSAGES={"invalid key":"🔑 کلید API نامعتبر است.","key not found":"🔑 کلید API پیدا نشد.","unauthorized":"🔑 دسترسی API رد شد.","invalid service":"❌ سرویس نامعتبر است.","invalid link":"❌ لینک نامعتبر است.","invalid quantity":"❌ تعداد نامعتبر است.","quantity must be":"❌ تعداد باید بین حداقل و حداکثر باشد.","insufficient balance":"⚠️ موجودی پنل سینتل کافی نیست.","not enough funds":"⚠️ موجودی پنل سینتل کافی نیست.","service unavailable":"❌ این سرویس فعلاً موجود نیست.","rate limit":"⚠️ درخواست زیاد شده؛ کمی صبر کنید.","timeout":"⏱ سرویس سینتل دیر پاسخ داد.","network error":"🌐 خطا در اتصال به سینتل."}
TELEGRAM_MARKERS=("telegram","تلگرام","t.me","channel","کانال","group","گروه","member","subscriber","reaction","ریاکشن"); INSTAGRAM_MARKERS=("instagram","اینستا","insta","instagr.am","reels","ریلز","story","استوری","فالوور","followers")
def _humanize_error(error):
    raw=str(error).strip(); low=raw.lower()
    for key,msg in ERROR_MESSAGES.items():
        if key in low:return msg
    return f"⚠️ پاسخ سینتل قابل قبول نیست: {raw[:180]}" if raw else "⚠️ پاسخ خالی از سینتل دریافت شد."
def clean_api_key(value:str)->str:
    value=str(value or "").strip().replace("\u200c",""); value=re.sub(r"^```(?:text|plain)?\s*|\s*```$","",value,flags=re.I).strip(); value=value.strip(' \"\'<>');
    if value.lower().startswith("bearer "):value=value[7:].strip()
    return value.split()[0] if value.split() else ""
def _as_int(v,default=0):
    try:return int(float(str(v).replace(",","").strip()))
    except (TypeError,ValueError):return default
def classify_service(s):
    explicit=str(s.get("platform") or s.get("network") or s.get("social") or "").lower(); text=" ".join(str(s.get(k,"")) for k in ("name","category","type","description","platform","network")).lower()
    if "instagram" in explicit or "insta" in explicit:return "instagram"
    if "telegram" in explicit:return "telegram"
    if any(x in text for x in INSTAGRAM_MARKERS):return "instagram"
    if any(x in text for x in TELEGRAM_MARKERS):return "telegram"
    return "telegram"
def normalize_service(raw):
    result=dict(raw); result["service"]=_as_int(raw.get("service",raw.get("service_id",raw.get("id",0)))); result["min"]=_as_int(raw.get("min",raw.get("min_quantity",raw.get("minimum",0)))); result["max"]=_as_int(raw.get("max",raw.get("max_quantity",raw.get("maximum",0)))); result["rate"]=str(raw.get("rate",raw.get("price","0"))); result["name"]=str(raw.get("name",raw.get("service_name","سرویس نامشخص"))).strip(); result["_platform"]=classify_service(result); return result
def _status_is_error(value): return str(value).strip().lower() in {"error","failed","fail","false","0","invalid","unauthorized"}
def _provider_error(result,fallback=""):
    if not isinstance(result,dict):return fallback
    status=result.get("status")
    # SINTELL can include a human-readable message alongside a successful balance.
    # Only treat message as an error when status explicitly says failure, or when an error field is present.
    for key in ("error","errors"):
        value=result.get(key)
        if value not in (None,"",False,0,"0","false","False","ok","success","true","1"):return str(value)
    if _status_is_error(status):return str(result.get("message") or result.get("msg") or status)
    return fallback
async def _request(key,action,**params):
    key=clean_api_key(key)
    if not key:raise SintelError("invalid key")
    payload={"key":key,"action":action,**params}
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(API_BASE,data=payload,headers={"Accept":"application/json"}) as response:
                body=await response.text(); status=response.status
    except asyncio.TimeoutError as exc:raise SintelError("timeout") from exc
    except aiohttp.ClientError as exc:raise SintelError(f"network error: {exc}") from exc
    try:result=json.loads(body)
    except json.JSONDecodeError as exc:raise SintelError(f"invalid JSON response: HTTP {status} {body[:120]}") from exc
    if status>=400:raise SintelError(_provider_error(result,f"HTTP {status}"))
    error=_provider_error(result,"")
    if error:raise SintelError(error)
    return result
class SintelClient:
    def __init__(self,api_key):
        self.api_key=clean_api_key(api_key)
        if not self.api_key:raise SintelError("invalid key")
    async def get_balance(self):
        result=await _request(self.api_key,"balance")
        if isinstance(result,dict):
            value=result.get("balance",result.get("funds",result.get("credit")))
            if value is not None:
                try:return float(value)
                except (TypeError,ValueError):pass
        raise SintelError("invalid balance response")
    async def test_connection(self):return await _request(self.api_key,"balance")
    async def get_services(self,lang="fa",use_cache=True):
        global _catalog_cache,_catalog_cache_time; now=time.time()
        if use_cache and _catalog_cache is not None and now-_catalog_cache_time<CATALOG_CACHE_TTL:return _catalog_cache
        result=await _request(self.api_key,"services",lang=lang)
        if isinstance(result,dict):result=result.get("services",result.get("data",result.get("items",[])))
        services=[normalize_service(x) for x in result if isinstance(x,dict)] if isinstance(result,list) else []; _catalog_cache,_catalog_cache_time=services,now; return services
    async def create_order(self,service_id,link,quantity):
        result=await _request(self.api_key,"add",service=int(service_id),link=link.strip(),quantity=int(quantity))
        if not isinstance(result,dict) or not result.get("order"):raise SintelError("order id missing")
        return result
    async def get_order_status(self,order_id):
        result=await _request(self.api_key,"status",order=int(order_id)); result=result[0] if isinstance(result,list) and result else result
        if not isinstance(result,dict):raise SintelError("status missing")
        return result
    async def cancel_order(self,order_id):return bool(await _request(self.api_key,"cancel",orders=str(int(order_id))))
    async def refill_order(self,order_id):return bool(await _request(self.api_key,"refill",order=int(order_id)))
def invalidate_catalog_cache():
    global _catalog_cache,_catalog_cache_time; _catalog_cache=None; _catalog_cache_time=0.0
def masked_key(key):return mask(key)
