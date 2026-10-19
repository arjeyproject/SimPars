"""Panelix catalog synchronization with dynamic Persian categories."""
from __future__ import annotations
import asyncio,json,logging,time
from decimal import Decimal,InvalidOperation,ROUND_CEILING
from typing import Any
import database as db
from services.sintel import PanelixClient,PanelixError,_humanize_error
log=logging.getLogger(__name__); _sync_lock=asyncio.Lock()
PLATFORM_LABELS={"instagram":("📸","اینستاگرام"),"telegram":("✈️","تلگرام"),"threads":("🧵","تردز"),"whatsapp":("🟢","واتساپ"),"rubika":("🟣","روبیکا"),"eitaa":("🟠","ایتا"),"aparat":("▶️","آپارات"),"youtube":("▶️","یوتیوب"),"facebook":("🔵","فیسبوک"),"twitter":("🐦","توییتر / ایکس"),"spotify":("🎧","اسپاتیفای"),"tiktok":("🎵","تیک‌تاک"),"other":("📱","سایر شبکه‌های اجتماعی")}
# Kept as a compatibility view for old imports; services still come only from Panelix.
SERVICE_CATEGORIES={p:{"emoji":e,"title":t,"subcategories":{k:{"emoji":"📦","title":k,"keywords":[]} for k in ("followers","likes","views","comments","story","reactions","boost","shares","watch","other")}} for p,(e,t) in PLATFORM_LABELS.items()}
def _text(*v): return " ".join(str(x or "") for x in v).lower()
def classify_platform(name,category,description=""):
    t=_text(name,category,description); groups={"instagram":("instagram","اینستا","فالوور اینست"),"telegram":("telegram","تلگرام","t.me"),"threads":("threads","تردز"),"whatsapp":("whatsapp","واتساپ"),"rubika":("rubika","روبیکا","روبینو"),"eitaa":("eitaa","ایتا"),"aparat":("aparat","آپارات"),"youtube":("youtube","یوتیوب"),"facebook":("facebook","فیسبوک"),"twitter":("twitter","توییتر","x.com"),"spotify":("spotify","اسپاتیفای"),"tiktok":("tiktok","تیک تاک","تیک‌تاک")}
    return next((p for p,m in groups.items() if any(x in t for x in m)),"other")
def classify_service(s): return classify_platform(s.get("name",""),s.get("category",""),s.get("description",s.get("desc","")))
def _subcategory(name,category,description=""):
    t=_text(name,category,description); groups={"followers":("follower","فالوور","member","ممبر","subscriber","عضو"),"likes":("like","لایک"),"views":("view","بازدید","play","پخش"),"comments":("comment","کامنت"),"story":("story","استوری"),"reactions":("reaction","ری‌اکشن","واکنش"),"boost":("boost","بوست"),"shares":("share","اشتراک","سیو"),"watch":("watch","تماشا")}
    return next((k for k,m in groups.items() if any(x in t for x in m)),"other")
def category_label(platform,subcategory): return {"followers":"فالوور و ممبر","likes":"لایک","views":"بازدید و پخش","comments":"کامنت","story":"استوری","reactions":"ری‌اکشن","boost":"بوست","shares":"سیو و اشتراک‌گذاری","watch":"زمان تماشا","other":"سایر خدمات"}.get(subcategory,"سایر خدمات")
def _price(rate,quantity,profit,unit,currency,fx):
    if unit not in ("per_1000","per_order") or not currency or currency=="unverified": return 0
    try:
        n=Decimal(str(rate))*(Decimal(quantity)/1000 if unit=="per_1000" else 1)
        if currency.upper()=="USD": n*=Decimal(str(fx))
        elif currency.upper() not in ("IRR","IRT","TOMAN","تومان"): return 0
        return int((n*(1+Decimal(str(profit or 0))/100)).quantize(Decimal("1"),rounding=ROUND_CEILING))
    except (InvalidOperation,TypeError,ValueError): return 0
def calculate_order_price(rate,quantity,**kwargs): return _price(rate,quantity,kwargs.get("profit","0"),kwargs.get("unit","unverified"),kwargs.get("currency",""),kwargs.get("fx_rate",0))
def calculate_selling_price(provider_cost,profit_percent): return max(0,int(Decimal(provider_cost)*(1+Decimal(str(profit_percent))/100)))
async def sync_catalog_from_provider(api_key):
    async with _sync_lock:
        started=int(time.time())
        try:
            services=await PanelixClient(api_key).get_services()
            if not services: raise PanelixError("empty or invalid services response; last valid catalog preserved")
            unit,currency=await db.get_setting("panelix_rate_unit"),await db.get_setting("panelix_currency"); now=int(time.time()); incoming={int(s["service"]):s for s in services}; c={"new":0,"updated":0,"unavailable":0,"errors":0}
            for sid,s in incoming.items():
                p=classify_platform(s["name"],s["category"],s.get("description","")); sub=_subcategory(s["name"],s["category"],s.get("description","")); raw=json.dumps(s,ensure_ascii=False,sort_keys=True); verified=int(unit in ("per_1000","per_order") and bool(currency and currency!="unverified"))
                async with db._db.execute("SELECT * FROM sintel_services WHERE service_id=?",(sid,)) as cur: old=await cur.fetchone()
                if old is None:
                    c["new"]+=1; await db._db.execute("INSERT INTO sintel_services(service_id,name,rate,min_quantity,max_quantity,platform,subcategory,extra_data,is_active,updated_at,provider,currency,rate_unit,price_verified,provider_category,provider_type,description,display_name,last_seen_at,unavailable_reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(sid,s["name"],s["rate"],s["min"],s["max"],p,sub,raw,1,now,"panelix",currency,unit,verified,s["category"],s["type"],s.get("description",""),"",now,""))
                else:
                    changed=any(str(old[k])!=str(v) for k,v in (("name",s["name"]),("rate",s["rate"]),("min_quantity",s["min"]),("max_quantity",s["max"]),("extra_data",raw),("platform",p),("subcategory",sub)))
                    c["updated"]+=int(changed); await db._db.execute("UPDATE sintel_services SET name=?,rate=?,min_quantity=?,max_quantity=?,platform=?,subcategory=?,extra_data=?,is_active=1,updated_at=?,provider='panelix',currency=?,rate_unit=?,price_verified=?,provider_category=?,provider_type=?,description=?,last_seen_at=?,unavailable_reason='' WHERE service_id=?",(s["name"],s["rate"],s["min"],s["max"],p,sub,raw,now,currency,unit,verified,s["category"],s["type"],s.get("description",""),now,sid))
            marks=','.join('?'*len(incoming)); async with db._db.execute(f"SELECT service_id FROM sintel_services WHERE provider='panelix' AND is_active=1 AND service_id NOT IN ({marks})",tuple(incoming)) as cur: removed=[r[0] for r in await cur.fetchall()]
            c["unavailable"]=len(removed); await db._db.executemany("UPDATE sintel_services SET is_active=0,unavailable_reason=?,updated_at=? WHERE service_id=?",[("در فهرست فعلی پنلیکس نیست",now,x) for x in removed]); result={"success":True,"total":len(incoming),**c}; await db._db.execute("INSERT INTO panelix_sync_log(started_at,finished_at,success,total,new_count,updated_count,unavailable_count,detail) VALUES(?,?,?,?,?,?,?,?)",(started,now,1,len(incoming),c["new"],c["updated"],c["unavailable"],json.dumps(result,ensure_ascii=False))); await db._db.commit(); await db.set_setting("panelix_last_sync",str(now)); await db.set_setting("panelix_last_sync_result",json.dumps(result,ensure_ascii=False)); return result
        except Exception as exc:
            log.exception("Panelix catalog sync failed"); result={"success":False,"total":0,"new":0,"updated":0,"unavailable":0,"errors":1,"error":_humanize_error(exc)}
            try: await db._db.execute("INSERT INTO panelix_sync_log(started_at,finished_at,success,error_count,detail) VALUES(?,?,?,?,?)",(started,int(time.time()),0,1,json.dumps(result,ensure_ascii=False))); await db._db.commit()
            except Exception: log.exception("sync log failed")
            return result
async def get_catalog_by_subcategory(platform,subcategory):
    async with db._db.execute("SELECT * FROM sintel_services WHERE provider='panelix' AND platform=? AND subcategory=? AND is_active=1 AND price_verified=1 ORDER BY display_order,name",(platform,subcategory)) as cur:return [dict(r) for r in await cur.fetchall()]
async def get_cached_catalog(platform=None):
    sql="SELECT * FROM sintel_services WHERE provider='panelix' AND is_active=1"+(" AND platform=?" if platform else "")+" ORDER BY platform,subcategory,display_order,name"
    async with db._db.execute(sql,(platform,) if platform else ()) as cur:return [dict(r) for r in await cur.fetchall()]
async def get_service_by_id(service_id):
    async with db._db.execute("SELECT * FROM sintel_services WHERE provider='panelix' AND service_id=? AND is_active=1 AND price_verified=1",(int(service_id),)) as cur:
        row=await cur.fetchone(); return dict(row) if row else None
