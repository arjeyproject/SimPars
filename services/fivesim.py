"""Provider client with complete country/operator availability."""
from __future__ import annotations
import asyncio, json, time
from typing import Any
import aiohttp
API_BASE="https://5sim.net/v1"
_TIMEOUT=aiohttp.ClientTimeout(total=25)
PRICE_CACHE_TTL=60
COUNTRY_CACHE_TTL=6*3600
_price_cache={}; _options_cache={}; _all_prices_cache=None; _country_cache={"time":0.0,"data":{}}
class FiveSimError(Exception): pass
ERROR_MESSAGES={"unauthorized":"🔑 اتصال سرویس فروش تنظیم نشده یا کلید آن نامعتبر است.","no free phones":"😕 شماره‌ای برای این کشور موجود نیست.","not enough user balance":"⚠️ موجودی تامین‌کننده موقتاً کافی نیست.","not enough rating":"⚠️ امکان خرید موقتاً وجود ندارد.","no product":"❌ این سرویس موجود نیست.","bad country":"❌ کشور نامعتبر است.","bad operator":"❌ اپراتور نامعتبر است.","server offline":"🔌 سرور تامین‌کننده موقتاً در دسترس نیست.","order not found":"↩️ سفارش دیگر وجود ندارد؛ مبلغ به کیف پول برمی‌گردد.","order expired":"↩️ سفارش منقضی شده؛ مبلغ برمی‌گردد.","banned":"🚫 سفارش مسدود شد؛ مبلغ به کیف پول برمی‌گردد.","ban":"🚫 سفارش مسدود شد؛ مبلغ به کیف پول برمی‌گردد.","network error":"🌐 خطا در اتصال به سرویس فروش."}
def humanize(error):
    text=str(error).lower(); return next((v for k,v in ERROR_MESSAGES.items() if k in text),"⚠️ خطا در ارتباط با سرویس فروش.")
async def _request(path,token=None,params=None):
    headers={"Accept":"application/json"}
    if token: headers["Authorization"]=f"Bearer {token}"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(API_BASE+path,headers=headers,params=params) as resp:
                status,text=resp.status,await resp.text()
    except (aiohttp.ClientError,asyncio.TimeoutError) as exc: raise FiveSimError(f"network error: {exc}") from exc
    if status==401: raise FiveSimError("unauthorized")
    try: data=json.loads(text)
    except ValueError as exc: raise FiveSimError(text.strip() or f"http {status}") from exc
    if status>=400: raise FiveSimError(text.strip() or f"http {status}")
    return data
def _options(operators: Any):
    if not isinstance(operators,dict): return []
    result=[]
    for operator,info in operators.items():
        if not isinstance(info,dict): continue
        try: cost,count=float(info.get("cost")),int(info.get("count") or 0)
        except (TypeError,ValueError): continue
        if cost>0 and count>0: result.append((str(operator),cost,count))
    return sorted(result,key=lambda x:x[1])
def _best(operators):
    values=_options(operators); return values[0] if values else None
def _payload_for_product(payload,product):
    if isinstance(payload,dict) and product and isinstance(payload.get(product),dict): return payload[product]
    return payload
def _normalize(payload,product=None):
    payload=_payload_for_product(payload,product); result={}
    if not isinstance(payload,dict): return result
    for country,operators in payload.items():
        best=_best(operators)
        if best: result[str(country)]=best
    return result
def _normalize_options(payload,product):
    payload=_payload_for_product(payload,product); result={}
    if not isinstance(payload,dict): return result
    for country,operators in payload.items():
        values=_options(operators)
        if values: result[str(country)]=values
    return result
def _normalize_all(payload):
    result={}
    if not isinstance(payload,dict): return result
    for country,products in payload.items():
        if not isinstance(products,dict): continue
        for product,operators in products.items():
            best=_best(operators)
            if best: result.setdefault(str(product),{})[str(country)]=best
    return result
async def get_all_prices(use_cache=True):
    global _all_prices_cache
    now=time.time()
    if use_cache and _all_prices_cache and now-_all_prices_cache[0]<PRICE_CACHE_TTL: return _all_prices_cache[1]
    result=_normalize_all(await _request("/guest/prices")); _all_prices_cache=(now,result); return result
async def get_product_prices(product,use_cache=True):
    now=time.time(); cached=_price_cache.get(product)
    if use_cache and cached and now-cached[0]<PRICE_CACHE_TTL: return cached[1]
    result=_normalize(await _request("/guest/prices",params={"product":product}),product); _price_cache[product]=(now,result); return result
async def get_product_options(product,use_cache=True):
    now=time.time(); cached=_options_cache.get(product)
    if use_cache and cached and now-cached[0]<PRICE_CACHE_TTL: return cached[1]
    result=_normalize_options(await _request("/guest/prices",params={"product":product}),product); _options_cache[product]=(now,result); return result
async def get_countries():
    now=time.time()
    if _country_cache["data"] and now-_country_cache["time"]<COUNTRY_CACHE_TTL: return _country_cache["data"]
    data=await _request("/guest/countries")
    if isinstance(data,dict): _country_cache.update(time=now,data=data); return data
    return {}
async def countries_safe():
    try: return await get_countries()
    except FiveSimError: return _country_cache["data"] or {}
class FiveSimClient:
    def __init__(self,token):
        if not token: raise FiveSimError("unauthorized")
        self.token=token
    async def profile(self): return await _request("/user/profile",self.token)
    async def buy(self,country,operator,product):
        data=await _request(f"/user/buy/activation/{country}/{operator}/{product}",self.token)
        if not isinstance(data,dict) or "id" not in data or not data.get("phone"): raise FiveSimError(str(data))
        return data
    async def check(self,order_id): return await _request(f"/user/check/{order_id}",self.token)
    async def cancel(self,order_id): return await _request(f"/user/cancel/{order_id}",self.token)
    async def finish(self,order_id): return await _request(f"/user/finish/{order_id}",self.token)
    async def ban(self,order_id): return await _request(f"/user/ban/{order_id}",self.token)
