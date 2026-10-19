"""ProSMM order lifecycle with conservative timeout handling."""
from __future__ import annotations
import asyncio, logging, time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
import database as db
from services.sintel import SintelClient, SintelError, _humanize_error
log = logging.getLogger(__name__)
ORDER_STATUS_MAP = {"Pending":"PENDING","Processing":"PROCESSING","In progress":"PROCESSING","Completed":"COMPLETED","Partial":"PARTIAL","Canceled":"CANCELED","Cancelled":"CANCELED"}
FINAL_STATUSES = ("COMPLETED", "PARTIAL", "CANCELED", "REFUNDED")
@dataclass
class OrderResult:
    success: bool
    order_id: int | None = None
    provider_order_id: str | None = None
    error: str | None = None
    status: str = "PENDING"
@dataclass
class OrderStatus:
    status: str
    remains: int = 0
    error: str | None = None
async def create_sintel_order(user_id:int, service_id:int, link:str, quantity:int, provider_cost:int, selling_price:int)->OrderResult:
    if quantity <= 0 or selling_price <= 0: return OrderResult(False, error="مقدار سفارش نامعتبر است.")
    user=await db.get_user(user_id)
    if not user: return OrderResult(False, error="کاربر پیدا نشد.")
    api_key=await db.get_setting("sintel_api")
    if not api_key: return OrderResult(False, error="API پروSMM تنظیم نشده است.")
    if not await db.deduct_balance(user_id, selling_price): return OrderResult(False, error="موجودی کافی نیست.")
    try:
        result=await SintelClient(api_key).create_order(service_id, link, quantity)
        provider_order_id=str(result.get("order") or "").strip()
        if not provider_order_id: raise SintelError("order id missing")
        order_id=await _save_order_to_db(user_id, provider_order_id, service_id, link, quantity, provider_cost, selling_price, "PENDING")
        return OrderResult(True, order_id, provider_order_id)
    except SintelError as exc:
        # An add timeout is ambiguous. Never credit the wallet until reconciliation proves no provider order exists.
        if "timeout" in str(exc).lower() or "network error" in str(exc).lower():
            try:
                matches=await SintelClient(api_key).find_orders_by_link(link, limit=10)
                candidate=None
                if isinstance(matches, list) and len(matches)==1: candidate=matches[0]
                elif isinstance(matches, dict) and matches.get("order"): candidate=matches
                if isinstance(candidate, dict) and candidate.get("order"):
                    provider_order_id=str(candidate["order"]); order_id=await _save_order_to_db(user_id, provider_order_id, service_id, link, quantity, provider_cost, selling_price, "PENDING")
                    return OrderResult(True, order_id, provider_order_id, status="PENDING")
            except Exception: log.warning("ProSMM ambiguous order reconciliation failed", exc_info=True)
            await db.add_balance(user_id, selling_price)
            return OrderResult(False, error="پاسخ تأمین‌کننده نامشخص بود؛ مبلغ برگشت خورد. قبل از تلاش دوباره وضعیت سفارش بررسی شد.", status="UNKNOWN")
        await db.add_balance(user_id, selling_price)
        return OrderResult(False, error=_humanize_error(exc))
    except Exception:
        await db.add_balance(user_id, selling_price)
        log.exception("Unexpected ProSMM order error")
        return OrderResult(False, error="خطای داخلی؛ مبلغ برگشت خورد.")
async def _save_order_to_db(user_id:int, provider_order_id:str, service_id:int, link:str, quantity:int, provider_cost:int, selling_price:int, status:str)->int:
    now=int(time.time())
    async with db._db.execute("INSERT INTO sintel_orders(user_id,provider_order_id,service_id,link,quantity,provider_cost,selling_price,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(user_id,provider_order_id,service_id,link,quantity,provider_cost,selling_price,status,now,now)) as cur:
        await db._db.commit(); return int(cur.lastrowid)
async def get_sintel_order(order_id:int)->dict[str,Any]|None:
    async with db._db.execute("SELECT * FROM sintel_orders WHERE id=?",(order_id,)) as cur:
        row=await cur.fetchone(); return dict(row) if row else None
async def get_order_status_from_provider(order_id:int)->OrderStatus:
    order=await get_sintel_order(order_id)
    if not order:return OrderStatus("UNKNOWN",error="سفارش پیدا نشد.")
    key=await db.get_setting("sintel_api")
    if not key:return OrderStatus(order["status"],error="API پروSMM تنظیم نشده.")
    try:
        result=await SintelClient(key).get_order_status(int(order["provider_order_id"]))
        mapped=ORDER_STATUS_MAP.get(str(result.get("status","")).strip(),order["status"])
        remains=max(0,int(result.get("remains") or 0)); await _update_order_status(order_id,mapped,remains)
        return OrderStatus(mapped,remains)
    except (SintelError,ValueError,TypeError) as exc:
        return OrderStatus(order["status"],error=_humanize_error(exc))
async def _update_order_status(order_id:int,status:str,remains:int=0)->None:
    await db._db.execute("UPDATE sintel_orders SET status=?,remains=?,updated_at=? WHERE id=? AND status NOT IN ('COMPLETED','PARTIAL','CANCELED','REFUNDED')",(status,remains,int(time.time()),order_id)); await db._db.commit()
async def get_user_sintel_orders(user_id:int,limit:int=20)->list[dict[str,Any]]:
    async with db._db.execute("SELECT * FROM sintel_orders WHERE user_id=? ORDER BY id DESC LIMIT ?",(user_id,limit)) as cur:return [dict(r) for r in await cur.fetchall()]
async def refund_sintel_order(order_id:int,reason:str="")->bool:
    order=await get_sintel_order(order_id)
    if not order or order["status"] in FINAL_STATUSES:return False
    cur=await db._db.execute("UPDATE sintel_orders SET status='REFUNDED',updated_at=? WHERE id=? AND status NOT IN ('COMPLETED','PARTIAL','CANCELED','REFUNDED')",(int(time.time()),order_id)); await db._db.commit()
    if cur.rowcount!=1:return False
    await db.add_balance(order["user_id"],order["selling_price"]); return True
async def sync_all_pending_orders(bot=None)->dict[str,int]:
    key=await db.get_setting("sintel_api")
    if not key:return {"skipped":0,"updated":0,"errors":0}
    async with db._db.execute("SELECT id,status FROM sintel_orders WHERE status NOT IN ('COMPLETED','PARTIAL','CANCELED','REFUNDED') ORDER BY id DESC LIMIT 100") as cur: orders=[dict(r) for r in await cur.fetchall()]
    stats={"updated":0,"errors":0}
    for order in orders:
        try:
            status=await get_order_status_from_provider(order["id"])
            if status.status!=order["status"]:stats["updated"]+=1
        except Exception:stats["errors"]+=1
        await asyncio.sleep(.1)
    return stats
def calculate_order_price(rate:str,quantity:int)->int:
    try:return int((Decimal(str(rate))*Decimal(str(quantity))/Decimal("1000")).quantize(Decimal("1")))
    except (InvalidOperation,ValueError,TypeError):return 0
def format_order_status_text(status:str)->str:
    return {"PENDING":"⏳ در انتظار","PROCESSING":"🔄 در حال انجام","COMPLETED":"✅ تکمیل شده","PARTIAL":"⚠️ تکمیل جزئی","CANCELED":"❌ لغو شده","REFUNDED":"↩️ برگشت داده شده","UNKNOWN":"⚠️ نیازمند بررسی"}.get(status,status)
