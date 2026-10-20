"""5SIM client with validated inventory and pinned operator selection."""
from __future__ import annotations
import asyncio,json,time
import aiohttp
API_BASE="https://5sim.net/v1"; _TIMEOUT=aiohttp.ClientTimeout(total=25); PRICE_CACHE_TTL=60; COUNTRY_CACHE_TTL=21600
_price_cache={}; _options_cache={}; _all_prices_cache=None; _country_cache={"time":0.0,"data":{}}; _quality_cache={}
_last_refresh={"time":0.0,"products":0,"countries":0}
class FiveSimError(Exception): pass
class PurchaseUnknownError(FiveSimError):
    """The provider may have created an activation but the response was lost."""
ERROR_MESSAGES={"unauthorized":"🔑 اتصال سرویس فروش تنظیم نشده یا کلید آن نامعتبر است.","no free phones":"😕 شماره‌ای برای این کشور موجود نیست.","not enough user balance":"⚠️ موجودی تامین‌کننده موقتاً کافی نیست.","not enough rating":"⚠️ امکان خرید موقتاً وجود ندارد.","no product":"❌ این سرویس موجود نیست.","bad country":"❌ کشور نامعتبر است.","bad operator":"❌ اپراتور نامعتبر است.","server offline":"🔌 سرور تامین‌کننده موقتاً در دسترس نیست.","order not found":"↩️ سفارش دیگر وجود ندارد؛ مبلغ به کیف پول برمی‌گردد.","order expired":"↩️ سفارش منقضی شده؛ مبلغ برمی‌گردد.","banned":"🚫 سفارش مسدود شد؛ مبلغ به کیف پول برمی‌گردد.","ban":"🚫 سفارش مسدود شد؛ مبلغ به کیف پول برمی‌گردد.","network error":"🌐 خطا در اتصال به سرویس فروش."}
def humanize(error):
    text=str(error).lower(); return next((v for k,v in ERROR_MESSAGES.items() if k in text),"⚠️ خطا در ارتباط با سرویس فروش.")
def _token(t):
    v=str(t or "").strip(); return v[7:].strip() if v.lower().startswith("bearer ") else v
def _message(data,fallback="provider error"):
    if isinstance(data,dict):
        for key in ("message","error","msg","detail"):
            if data.get(key): return str(data[key])
    return "; ".join(map(str,data)) if isinstance(data,list) else str(data).strip() or fallback
async def _request(path,token=None,params=None):
    headers={"Accept":"application/json"}
    if token: headers["Authorization"]=f"Bearer {_token(token)}"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(API_BASE+path,headers=headers,params=params) as resp: status,body=resp.status,await resp.text()
    except (aiohttp.ClientError,asyncio.TimeoutError) as exc: raise FiveSimError(f"network error: {exc}") from exc
    try:data=json.loads(body)
    except ValueError as exc:raise FiveSimError(body.strip() or f"http {status}") from exc
    if status==401:raise FiveSimError("unauthorized")
    if status>=400:raise FiveSimError(_message(data,f"http {status}"))
    return data
def _number(v,default=0.0):
    try:return float(v)
    except (TypeError,ValueError):return default
def _options(operators,country=None,product=None):
    if not isinstance(operators,dict):return []
    result=[]
    for operator,info in operators.items():
        if not isinstance(info,dict):continue
        cost=_number(info.get("cost")); count=int(_number(info.get("count")))
        if cost<=0 or count<=0:continue
        # 5Sim نرخ موفقیت اپراتور را در فیلد rate (درصد) می‌فرستد
        quality=max(_number(info.get(k),-1) for k in ("rate","quality","rating","success_rate","successRate","delivery_rate","success"))
        if quality<0:quality=0.0
        if quality>1:quality=min(100.0,quality)/100.0
        _quality_cache[(str(country or ""),str(product or ""),str(operator))]=quality; result.append((str(operator),cost,count))
    return sorted(result,key=lambda x:x[1],reverse=True)
def choose_operator(values,country="",product="",preferred=()):
    """بهترین اپراتور: اول بالاترین کیفیت (نرخ موفقیت)، بعد گران‌ترین قیمت."""
    if not values:return None
    preferred={str(x).strip().lower() for x in preferred if str(x).strip()}
    def key(item):
        op,cost,count=item; quality=round(_quality_cache.get((str(country),str(product),str(op)),0.0),2); pref=1 if op.lower() in preferred else 0
        return (quality,cost,pref,count)
    return max(values,key=key)
def _best(operators,country=None,product=None,preferred=()):return choose_operator(_options(operators,country,product),country,product,preferred)
def _payload(payload,product):return payload.get(product) if isinstance(payload,dict) and isinstance(payload.get(product),dict) else payload
def _normalize(payload,product=None):
    payload=_payload(payload,product); result={}
    if not isinstance(payload,dict):return result
    for country,operators in payload.items():
        best=_best(operators,country,product)
        if best:result[str(country)]=best
    return result
def _normalize_options(payload,product):
    payload=_payload(payload,product); result={}
    if not isinstance(payload,dict):return result
    for country,operators in payload.items():
        values=_options(operators,country,product)
        if values:result[str(country)]=values
    return result
def _normalize_all(payload):
    result={}
    if not isinstance(payload,dict):return result
    for country,products in payload.items():
        if not isinstance(products,dict):continue
        for product,operators in products.items():
            best=_best(operators,country,product)
            if best:result.setdefault(str(product),{})[str(country)]=best
    return result
async def get_all_prices(use_cache=True):
    global _all_prices_cache; now=time.time()
    if use_cache and _all_prices_cache and now-_all_prices_cache[0]<PRICE_CACHE_TTL:return _all_prices_cache[1]
    result=_normalize_all(await _request("/guest/prices")); _all_prices_cache=(now,result); return result
async def get_product_prices(product,use_cache=True):
    now=time.time(); cached=_price_cache.get(product)
    if use_cache and cached and now-cached[0]<PRICE_CACHE_TTL:return cached[1]
    result=_normalize(await _request("/guest/prices",params={"product":product}),product); _price_cache[product]=(now,result); return result
async def get_product_options(product,use_cache=True):
    now=time.time(); cached=_options_cache.get(product)
    if use_cache and cached and now-cached[0]<PRICE_CACHE_TTL:return cached[1]
    result=_normalize_options(await _request("/guest/prices",params={"product":product}),product); _options_cache[product]=(now,result); return result
async def refresh_all():
    """دریافت واقعی همه قیمت‌ها و کشورها از 5Sim و جایگزینی کش‌ها."""
    global _all_prices_cache
    payload=await _request("/guest/prices")
    if not isinstance(payload,dict) or not payload:raise FiveSimError("empty prices response")
    now=time.time(); by_product={}
    for country,products in payload.items():
        if not isinstance(products,dict):continue
        for product,operators in products.items():by_product.setdefault(str(product),{})[str(country)]=operators
    all_best={}
    for product,countries in by_product.items():
        _options_cache[product]=(now,_normalize_options(countries,product)); best=_normalize(countries,product); _price_cache[product]=(now,best)
        if best:all_best[product]=best
    _all_prices_cache=(now,all_best)
    _country_cache["time"]=0.0; await countries_safe()
    _last_refresh.update(time=now,products=len(all_best),countries=len({c for p in all_best.values() for c in p}))
    return dict(_last_refresh)
async def get_countries():
    now=time.time()
    if _country_cache["data"] and now-_country_cache["time"]<COUNTRY_CACHE_TTL:return _country_cache["data"]
    data=await _request("/guest/countries")
    if isinstance(data,dict):_country_cache.update(time=now,data=data);return data
    return {}
async def countries_safe():
    try:return await get_countries()
    except FiveSimError:return _country_cache["data"] or {}
class FiveSimClient:
    def __init__(self,token):
        self.token=_token(token)
        if not self.token:raise FiveSimError("unauthorized")
    async def profile(self):return await _request("/user/profile",self.token)
    async def buy(self,country,operator,product):
        selected=str(operator or "").strip()
        if not selected or selected.lower()=="any":raise FiveSimError("bad operator: a pinned operator is required")
        try:data=await _request(f"/user/buy/activation/{country}/{selected}/{product}",self.token)
        except FiveSimError as exc:
            if "network error" in str(exc).lower() or "timeout" in str(exc).lower():raise PurchaseUnknownError(str(exc)) from exc
            raise
        if not isinstance(data,dict) or not data.get("id") or not data.get("phone"):raise FiveSimError(_message(data,"invalid purchase response"))
        if str(data.get("operator") or selected).strip().lower()!=selected.lower():raise FiveSimError("invalid purchase response: operator changed")
        return data
    async def check(self,order_id):return await _request(f"/user/check/{order_id}",self.token)
    async def cancel(self,order_id):return await _request(f"/user/cancel/{order_id}",self.token)
    async def finish(self,order_id):return await _request(f"/user/finish/{order_id}",self.token)
    async def ban(self,order_id):return await _request(f"/user/ban/{order_id}",self.token)
