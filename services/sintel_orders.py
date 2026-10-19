"""Panelix order lifecycle with atomic wallet protection."""
from __future__ import annotations
import asyncio, logging, time
from dataclasses import dataclass
from typing import Any
import database as db
from services.sintel import PanelixClient, PanelixError, _humanize_error

log = logging.getLogger(__name__)
ORDER_STATUS_MAP = {"Pending":"PENDING", "Processing":"PROCESSING", "In progress":"PROCESSING", "Completed":"COMPLETED", "Partial":"PARTIAL", "Canceled":"CANCELED", "Cancelled":"CANCELED"}
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


async def create_sintel_order(user_id: int, service_id: int, link: str, quantity: int, provider_cost: int, selling_price: int) -> OrderResult:
    if quantity <= 0 or selling_price <= 0: return OrderResult(False, error="مقدار سفارش نامعتبر است.")
    service = await db._db.execute("SELECT service_id,is_active,price_verified,min_quantity,max_quantity FROM sintel_services WHERE provider='panelix' AND service_id=?", (int(service_id),))
    row = await service.fetchone(); await service.close()
    if not row or not row[1] or not row[2] or quantity < row[3] or quantity > row[4]: return OrderResult(False, error="سرویس غیرفعال یا قیمت آن تأیید نشده است.")
    key = await db.get_setting("panelix_api")
    if not key: return OrderResult(False, error="کلید API پنلیکس تنظیم نشده است.")
    # Reserve customer funds before contacting the provider. The provider add call is one-shot.
    if not await db.deduct_balance(user_id, selling_price): return OrderResult(False, error="موجودی کافی نیست.")
    try:
        result = await PanelixClient(key).create_order(service_id, link, quantity)
        provider_order_id = str(result.get("order") or "").strip()
        if not provider_order_id: raise PanelixError("order id missing")
        order_id = await _save_order_to_db(user_id, provider_order_id, service_id, link, quantity, provider_cost, selling_price, "PENDING")
        return OrderResult(True, order_id, provider_order_id)
    except PanelixError as exc:
        # Panelix has no documented idempotency lookup in this API. An add timeout is UNKNOWN,
        # never an automatic refund and never a blind retry.
        if "timeout" in str(exc).lower() or "network error" in str(exc).lower():
            log.warning("ambiguous Panelix add for user=%s service=%s", user_id, service_id)
            return OrderResult(False, error="پاسخ پنلیکس نامشخص بود؛ مبلغ تا تعیین وضعیت سفارش برگشت نمی‌خورد. با پشتیبانی تماس بگیرید.", status="UNKNOWN")
        await db.add_balance(user_id, selling_price)
        return OrderResult(False, error=_humanize_error(exc))
    except Exception:
        log.exception("unexpected Panelix order error")
        return OrderResult(False, error="خطای داخلی؛ مبلغ تا بررسی سفارش محفوظ ماند.", status="UNKNOWN")


async def _save_order_to_db(user_id: int, provider_order_id: str, service_id: int, link: str, quantity: int, provider_cost: int, selling_price: int, status: str) -> int:
    now = int(time.time())
    async with db._db.execute("INSERT INTO sintel_orders(user_id,provider_order_id,service_id,link,quantity,provider_cost,selling_price,status,created_at,updated_at,provider,refund_applied) VALUES(?,?,?,?,?,?,?,?,?,?,?,0)", (user_id,provider_order_id,service_id,link,quantity,provider_cost,selling_price,status,now,now,"panelix")) as cur:
        await db._db.commit(); return int(cur.lastrowid)

async def get_sintel_order(order_id: int) -> dict[str, Any] | None:
    async with db._db.execute("SELECT * FROM sintel_orders WHERE id=?", (order_id,)) as cur:
        row = await cur.fetchone(); return dict(row) if row else None

async def get_order_status_from_provider(order_id: int) -> OrderStatus:
    order = await get_sintel_order(order_id)
    if not order: return OrderStatus("UNKNOWN", error="سفارش پیدا نشد.")
    key = await db.get_setting("panelix_api")
    if not key: return OrderStatus(order["status"], error="کلید API پنلیکس تنظیم نشده است.")
    try:
        result = await PanelixClient(key).get_order_status(int(order["provider_order_id"]))
        mapped = ORDER_STATUS_MAP.get(str(result.get("status", "")).strip(), order["status"])
        remains = max(0, int(float(result.get("remains") or 0))); await _update_order_status(order_id, mapped, remains); return OrderStatus(mapped, remains)
    except (PanelixError, ValueError, TypeError) as exc: return OrderStatus(order["status"], error=_humanize_error(exc))

async def _update_order_status(order_id: int, status: str, remains: int = 0) -> None:
    await db._db.execute("UPDATE sintel_orders SET status=?,remains=?,updated_at=? WHERE id=? AND status NOT IN ('COMPLETED','PARTIAL','CANCELED','REFUNDED')", (status,remains,int(time.time()),order_id)); await db._db.commit()

async def get_user_sintel_orders(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    async with db._db.execute("SELECT * FROM sintel_orders WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id,limit)) as cur: return [dict(r) for r in await cur.fetchall()]

async def refund_sintel_order(order_id: int, reason: str = "") -> bool:
    async with db._db.execute("BEGIN IMMEDIATE"):
        async with db._db.execute("SELECT user_id,selling_price,status,refund_applied FROM sintel_orders WHERE id=?", (order_id,)) as cur: order = await cur.fetchone()
        if not order or order[2] in FINAL_STATUSES or order[3]: await db._db.rollback(); return False
        cur = await db._db.execute("UPDATE sintel_orders SET status='REFUNDED',refund_applied=1,updated_at=? WHERE id=? AND refund_applied=0 AND status NOT IN ('COMPLETED','PARTIAL','CANCELED','REFUNDED')", (int(time.time()),order_id))
        if cur.rowcount != 1: await db._db.rollback(); return False
        await db._db.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (int(order[1]), int(order[0])))
        await db._db.commit(); return True

async def sync_all_pending_orders(bot=None) -> dict[str, int]:
    key = await db.get_setting("panelix_api")
    if not key: return {"skipped":0,"updated":0,"errors":0}
    async with db._db.execute("SELECT id,status FROM sintel_orders WHERE provider='panelix' AND status NOT IN ('COMPLETED','PARTIAL','CANCELED','REFUNDED') ORDER BY id DESC LIMIT 100") as cur: orders = [dict(r) for r in await cur.fetchall()]
    stats = {"updated":0,"errors":0}
    for order in orders:
        try:
            status = await get_order_status_from_provider(order["id"])
            if status.status != order["status"]: stats["updated"] += 1
        except Exception: stats["errors"] += 1
        await asyncio.sleep(.1)
    return stats

def calculate_order_price(rate: str, quantity: int, **kwargs) -> int:
    from services.sintel_catalog import calculate_order_price as _calculate
    return _calculate(rate, quantity, **kwargs)

def format_order_status_text(status: str) -> str:
    return {"PENDING":"⏳ در انتظار", "PROCESSING":"🔄 در حال انجام", "COMPLETED":"✅ تکمیل شده", "PARTIAL":"⚠️ تکمیل جزئی", "CANCELED":"❌ لغو شده", "REFUNDED":"↩️ برگشت داده شده", "UNKNOWN":"⚠️ نیازمند بررسی"}.get(status, status)
