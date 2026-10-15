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
    return f"⚠️ پاسخ سینتل: {raw[:220]}" if raw else "⚠️ پاسخ خالی از سینتل دریافت شد."
def clean_api_key(value:str)->str:
    value=str(value or "").strip().replace("\u200c",""); value=re.sub(r"^```(?:text|plain)?\s*|\s*```$","",value,flags=re.I).strip(); value=value.strip(' \"\'<>')
    if value.lower().startswith("bearer "):value=value[7:].strip()
    return value.split()[0] if value.split() else ""
def _as_int(v,default=0):
    try:return int(float(str(v).replace(",","").strip()))
    except (TypeError,ValueError):return default
def _walk_value(value,keys):
    if isinstance(value,dict):
        for key in keys:
            if key in value and value[key] not in (None,""):return value[key]
        for child in value.values():
            found=_walk_value(child,keys)
            if found is not None:return found
    elif isinstance(value,list):
        for child in value:
            found=_walk_value(child,keys)
            if found is not None:return found
    return None
def classify_service(s):
    explicit=str(s.get("platform") or s.get("network") or s.get("social") or "").lower(); text=" ".join(str(s.get(k,"")) for k in ("name","category","type","description","platform","network")).lower()
    if "instagram" in explicit or "insta" in explicit:return "instagram"
    if "telegram" in explicit:return "telegram"
    if any(x in text for x in INSTAGRAM_MARKERS):return "instagram"
    if any(x in text for x in TELEGRAM_MARKERS):return "telegram"
    return "telegram"
def normalize_service(raw):
    result=dict(raw); result["service"]=_as_int(raw.get("service",raw.get("service_id",raw.get("id",0)))); result["min"]=_as_int(raw.get("min",raw.get("min_quantity",raw.get("minimum",0)))); result["max"]=_as_int(raw.get("max",raw.get("max_quantity",raw.get("maximum",0)))); result["rate"]=str(raw.get("rate",raw.get("price","0"))); result["name"]=str(raw.get("name",raw.get("service_name","سرویس نامشخص"))).strip(); result["_platform"]=classify_service(result); return result
def _status_is_error(value):return str(value).strip().lower() in {"error","failed","fail","false","0","invalid","unauthorized"}
def _provider_error(result,fallback=""):
    if not isinstance(result,dict):return fallback
    for key in ("error","errors"):
        value=result.get(key)
        if value not in (None,"",False,0,"0","false","False","ok","success","true","1"):return str(value)
    status=result.get("status")
    if _status_is_error(status):return str(result.get("message") or result.get("msg") or status)
    return fallback
async def _request(key,action,**params):
    key=clean_api_key(key)
    if not key:raise SintelError("invalid key")
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(API_BASE,data={"key":key,"action":action,**params},headers={"Accept":"application/json"}) as response:
                body=await response.text(); status=response.status
    except asyncio.TimeoutError as exc:raise SintelError("timeout") from exc
    except aiohttp.ClientError as exc:raise SintelError(f"network error: {exc}") from exc
    try:result=json.loads(body)
    except json.JSONDecodeError as exc:raise SintelError(f"invalid JSON response: HTTP {status} {body[:120]}") from exc
    error=_provider_error(result,f"HTTP {status}" if status>=400 else "")
    if error:raise SintelError(error)
    return result
class SintelClient:
    def __init__(self,api_key):
        self.api_key=clean_api_key(api_key)
        if not self.api_key:raise SintelError("invalid key")
    async def get_balance(self):
        result=await _request(self.api_key,"balance"); value=_walk_value(result,("balance","funds","credit","wallet_balance"))
        if value is not None:
            try:return float(str(value).replace(",",""))
            except (TypeError,ValueError):pass
        raise SintelError(f"invalid balance response: {json.dumps(result,ensure_ascii=False)[:180]}")
    async def test_connection(self):return await _request(self.api_key,"balance")
    async def get_services(self,lang="fa",use_cache=True):
        global _catalog_cache,_catalog_cache_time; now=time.time()
        if use_cache and _catalog_cache is not None and now-_catalog_cache_time<CATALOG_CACHE_TTL:return _catalog_cache
        result=await _request(self.api_key,"services",lang=lang); result=result.get("services",result.get("data",result.get("items",[]))) if isinstance(result,dict) else result
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
