"""ProSMM API v2 client with safe non-retrying order creation."""
from __future__ import annotations
import asyncio, json, logging, os, re, socket, time
from typing import Any
import aiohttp
from utils import mask
log=logging.getLogger(__name__); API_BASE=os.getenv("PROSMM_API_URL","https://prosmm.io/api/v2").strip() or "https://prosmm.io/api/v2"; SINTEL_PROXY=os.getenv("PROSMM_PROXY","").strip() or os.getenv("SINTEL_PROXY","").strip() or None; FORCE_IPV4=os.getenv("PROSMM_FORCE_IPV4",os.getenv("SINTEL_FORCE_IPV4","1")).strip()!="0"; _TIMEOUT=aiohttp.ClientTimeout(total=40,connect=15,sock_connect=15,sock_read=30); _RETRIES=2; CATALOG_CACHE_TTL=300; _catalog_cache=None; _catalog_cache_time=0.0; _HEADERS={"Accept":"application/json, text/plain, */*","Accept-Encoding":"gzip, deflate","User-Agent":"SimParsBot/1.0"}
class SintelError(Exception): pass
ERROR_MESSAGES={"invalid key":"🔑 کلید API پروSMM نامعتبر است.","incorrect key":"🔑 کلید API پروSMM نامعتبر است.","key not found":"🔑 کلید API پروSMM پیدا نشد.","unauthorized":"🔑 دسترسی API پروSMM رد شد.","invalid service":"❌ سرویس نامعتبر است.","invalid link":"❌ لینک نامعتبر است.","invalid quantity":"❌ تعداد نامعتبر است.","quantity must be":"❌ تعداد باید بین حداقل و حداکثر باشد.","insufficient balance":"⚠️ موجودی پنل ProSMM کافی نیست.","not enough funds":"⚠️ موجودی پنل ProSMM کافی نیست.","rate limit":"⚠️ سقف درخواست API پر شده است.","timeout":"⏱ ProSMM دیر پاسخ داد.","network error":"🌐 خطا در اتصال به ProSMM."}
TELEGRAM_MARKERS=("telegram","تلگرام","t.me","channel","کانال","group","گروه","member","subscriber","reaction","ریاکشن"); INSTAGRAM_MARKERS=("instagram","اینستا","insta","instagr.am","reels","ریلز","story","استوری","فالوور","followers")
def _humanize_error(error):
    raw=str(error).strip(); low=raw.lower()
    for key,msg in ERROR_MESSAGES.items():
        if key in low:return msg
    return f"⚠️ پاسخ ProSMM: {raw[:220]}" if raw else "⚠️ پاسخ خالی از ProSMM دریافت شد."
def clean_api_key(value:str)->str:
    value=str(value or "").strip().replace("\u200c","").replace("\u200f","").replace("\u200e",""); value=re.sub(r"^```(?:text|plain)?\s*|\s*```$","",value,flags=re.I).strip().strip(' \"\'<>`')
    if value.lower().startswith("bearer "): value=value[7:].strip()
    return value.split()[0] if value.split() else ""
def _as_int(v,default=0):
    try:return int(float(str(v).replace(",","").strip()))
    except (TypeError,ValueError):return default
def classify_service(s):
    explicit=str(s.get("platform") or s.get("network") or "").lower(); text=" ".join(str(s.get(k,"")) for k in ("name","category","type","description")).lower()
    if "insta" in explicit:return "instagram"
    if "telegram" in explicit:return "telegram"
    if any(x in text for x in INSTAGRAM_MARKERS):return "instagram"
    if any(x in text for x in TELEGRAM_MARKERS):return "telegram"
    return "other"
def normalize_service(raw):
    r=dict(raw); r["service"]=_as_int(raw.get("service",raw.get("id",0))); r["min"]=_as_int(raw.get("min",0)); r["max"]=_as_int(raw.get("max",0)); r["rate"]=str(raw.get("rate","0")); r["name"]=str(raw.get("name","سرویس نامشخص")).strip(); r["_platform"]=classify_service(r); return r
def _provider_error(result): return str(result["error"]) if isinstance(result,dict) and result.get("error") not in (None,"",False) else ""
def _connector(): return aiohttp.TCPConnector(family=socket.AF_INET if FORCE_IPV4 else 0,ttl_dns_cache=300)
async def _post_once(payload):
    async with aiohttp.ClientSession(timeout=_TIMEOUT,connector=_connector(),headers=_HEADERS) as session:
        async with session.post(API_BASE,data=payload,proxy=SINTEL_PROXY) as response:return response.status,await response.text()
async def _request(key,action,**params):
    key=clean_api_key(key)
    if not key:raise SintelError("invalid key")
    payload={"key":key,"action":action,**{k:v for k,v in params.items() if v is not None}}
    # add is not safely retryable: a timeout may already have created a paid order.
    attempts=1 if action in {"add"} else _RETRIES+1; last=None
    for attempt in range(attempts):
        try: status,body=await _post_once(payload); break
        except (aiohttp.ServerTimeoutError,asyncio.TimeoutError) as exc:
            last=SintelError("timeout"); log.warning("ProSMM %s timeout attempt %d",action,attempt+1)
        except aiohttp.ClientError as exc:
            last=SintelError(f"network error: {exc}"); log.warning("ProSMM %s network attempt %d",action,attempt+1)
        if attempt+1<attempts: await asyncio.sleep(1.5*(attempt+1))
    else: raise last or SintelError("network error")
    try: result=json.loads(body)
    except json.JSONDecodeError as exc: raise SintelError(f"invalid JSON response: HTTP {status}") from exc
    error=_provider_error(result)
    if error: raise SintelError(error)
    if status>=400: raise SintelError(f"HTTP {status}")
    return result
class SintelClient:
    def __init__(self,api_key):
        self.api_key=clean_api_key(api_key)
        if not self.api_key:raise SintelError("invalid key")
    async def get_balance(self)->float:
        result=await _request(self.api_key,"balance")
        if isinstance(result,dict) and result.get("balance") is not None:
            try:return float(str(result["balance"]).replace(",",""))
            except ValueError:pass
        raise SintelError("invalid balance response")
    async def test_connection(self):return await _request(self.api_key,"balance")
    async def get_services(self,lang="fa",use_cache=True):
        global _catalog_cache,_catalog_cache_time; now=time.time()
        if use_cache and _catalog_cache is not None and now-_catalog_cache_time<CATALOG_CACHE_TTL:return _catalog_cache
        result=await _request(self.api_key,"services",lang=lang); services=[normalize_service(x) for x in result if isinstance(x,dict)] if isinstance(result,list) else []; _catalog_cache,_catalog_cache_time=services,now; return services
    async def create_order(self,service_id,link,quantity):
        result=await _request(self.api_key,"add",service=int(service_id),link=link.strip(),quantity=int(quantity))
        if not isinstance(result,dict) or not result.get("order"):raise SintelError("order id missing")
        return result
    async def find_orders_by_link(self,link,limit=5):return await _request(self.api_key,"orders",link=link.strip(),limit=int(limit))
    async def get_order_status(self,order_id):
        result=await _request(self.api_key,"status",order=int(order_id))
        if not isinstance(result,dict):raise SintelError("status missing")
        return result
    async def cancel_order(self,order_id):return bool(await _request(self.api_key,"cancel",orders=str(int(order_id))))
    async def refill_order(self,order_id):return bool(await _request(self.api_key,"refill",order=int(order_id)))
def invalidate_catalog_cache():
    global _catalog_cache,_catalog_cache_time; _catalog_cache=None; _catalog_cache_time=0.0
def masked_key(key):return mask(key)
