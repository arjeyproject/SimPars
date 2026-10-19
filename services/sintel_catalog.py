"""Verified live ProSMM catalog and conservative customer mappings."""
from __future__ import annotations
import json, logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
import database as db
from services.sintel import SintelClient, SintelError, _humanize_error, invalidate_catalog_cache
log=logging.getLogger(__name__)
# Premium and Stars are intentionally absent: generic SMM entries must never be mislabeled as subscriptions.
SERVICE_CATEGORIES={"telegram":{"emoji":"👥","title":"سرویس‌های تلگرام","subcategories":{"members":{"emoji":"👥","title":"ممبر تلگرام","keywords":["member","subscriber","عضو","مشترک"]},"views":{"emoji":"👁️","title":"بازدید پست","keywords":["view","بازدید"]},"reactions":{"emoji":"❤️","title":"ری‌اکشن","keywords":["reaction","ریاکشن"]}}},"instagram":{"emoji":"📸","title":"سرویس‌های اینستاگرام","subcategories":{"followers":{"emoji":"👥","title":"فالوور اینستاگرام","keywords":["followers","فالوور","follower"]},"likes":{"emoji":"❤️","title":"لایک پست","keywords":["like","لایک"]},"views":{"emoji":"▶️","title":"بازدید پست و ریلز","keywords":["view","بازدید","reel","ریلز"]},"story":{"emoji":"⭕","title":"بازدید استوری","keywords":["story","استوری"]},"comments":{"emoji":"💬","title":"کامنت اینستاگرام","keywords":["comment","کامنت"]}}}}
def _subcategory(platform:str,name:str,category:str)->str:
    text=f"{name} {category}".lower()
    for key,info in SERVICE_CATEGORIES.get(platform,{}).get("subcategories",{}).items():
        if any(k.lower() in text for k in info["keywords"]):return key
    return "other"
def calculate_order_price(rate:str|float,quantity:int)->int:
    try:return int((Decimal(str(rate))*Decimal(str(quantity))/Decimal("1000")).quantize(Decimal("1")))
    except (InvalidOperation,TypeError,ValueError):return 0
def calculate_selling_price(provider_cost:int,profit_percent:float)->int:return max(0,int(provider_cost+provider_cost*float(profit_percent)/100))
async def sync_catalog_from_provider(api_key:str)->dict[str,Any]:
    try:
        services=await SintelClient(api_key).get_services(use_cache=False)
        ids=[]; counts={"telegram":0,"instagram":0,"unknown":0}
        for s in services:
            sid=int(s.get("service",0)); rate=Decimal(str(s.get("rate","0")))
            if sid<=0 or rate<=0 or int(s.get("min",0))<=0 or int(s.get("max",0))<int(s.get("min",0)):continue
            platform=s.get("_platform","other")
            if platform not in ("telegram","instagram"):continue
            sub=_subcategory(platform,s.get("name",""),s.get("category",""))
            if sub=="other":continue
            extra=json.dumps({"type":s.get("type",""),"category":s.get("category",""),"platform":platform,"subcategory":sub,"refill":bool(s.get("refill",False)),"cancel":bool(s.get("cancel",False)),"description":s.get("description","")},ensure_ascii=False)
            await db._db.execute("INSERT INTO sintel_services(service_id,name,rate,min_quantity,max_quantity,platform,subcategory,extra_data,is_active,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?) ON CONFLICT(service_id) DO UPDATE SET name=excluded.name,rate=excluded.rate,min_quantity=excluded.min_quantity,max_quantity=excluded.max_quantity,platform=excluded.platform,subcategory=excluded.subcategory,extra_data=excluded.extra_data,is_active=1,updated_at=excluded.updated_at",(sid,s.get("name","سرویس"),str(rate),int(s.get("min")),int(s.get("max")),platform,sub,extra,int(datetime.now().timestamp())))
            ids.append(sid); counts[platform]+=1
        if ids:
            marks=",".join("?" for _ in ids); await db._db.execute(f"UPDATE sintel_services SET is_active=0 WHERE service_id NOT IN ({marks})",tuple(ids))
        await db._db.commit(); invalidate_catalog_cache(); return {"success":True,"total":len(ids),**counts}
    except SintelError as exc:return {"success":False,"error":_humanize_error(exc),"total":0}
    except Exception as exc:log.exception("catalog sync failed"); return {"success":False,"error":"خطای داخلی در همگام‌سازی کاتالوگ","total":0}
async def get_catalog_by_subcategory(platform:str,subcategory:str):
    async with db._db.execute("SELECT * FROM sintel_services WHERE platform=? AND subcategory=? AND is_active=1 ORDER BY name",(platform,subcategory)) as cur:return [dict(r) for r in await cur.fetchall()]
async def get_cached_catalog(platform:str|None=None):
    sql="SELECT * FROM sintel_services WHERE is_active=1"+(" AND platform=?" if platform else "")+" ORDER BY platform,subcategory,name"
    async with db._db.execute(sql,(platform,) if platform else ()) as cur:return [dict(r) for r in await cur.fetchall()]
async def get_service_by_id(service_id:int):
    async with db._db.execute("SELECT * FROM sintel_services WHERE service_id=? AND is_active=1",(int(service_id),)) as cur:
        row=await cur.fetchone(); return dict(row) if row else None
