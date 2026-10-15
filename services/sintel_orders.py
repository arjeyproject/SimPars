"""مدیریت سفارشات سینتل - ایجاد، پیگیری و بازگشت وجه."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import database as db
from services.sintel import SintelClient, SintelError, _humanize_error

log = logging.getLogger(__name__)

# وضعیت‌های سفارش سینتل
ORDER_STATUS_MAP = {
    "Pending": "PENDING",
    "Processing": "PROCESSING",
    "In progress": "PROCESSING",
    "Completed": "COMPLETED",
    "Partial": "PARTIAL",
    "Canceled": "CANCELED",
    "Cancelled": "CANCELED",
}

# وضعیت‌های نهایی (بسته شده)
FINAL_STATUSES = ("COMPLETED", "PARTIAL", "CANCELED")


@dataclass
class OrderResult:
    """نتیجه یک سفارش."""
    success: bool
    order_id: int | None = None
    provider_order_id: str | None = None
    error: str | None = None
    status: str = "PENDING"


@dataclass
class OrderStatus:
    """وضعیت یک سفارش."""
    status: str
    remains: int = 0
    error: str | None = None


async def create_sintel_order(
    user_id: int,
    service_id: int,
    link: str,
    quantity: int,
    provider_cost: int,
    selling_price: int,
) -> OrderResult:
    """
    ایجاد سفارش جدید سینتل.

    Args:
        user_id: شناسه کاربر
        service_id: شناسه سرویس سینتل
        link: لینک یا شناسه هدف
        quantity: تعداد سفارش
        provider_cost: هزینه تمام‌شده به تومان
        selling_price: قیمت فروش به تومان

    Returns:
        نتیجه سفارش
    """
    # بررسی موجودی کاربر
    user = await db.get_user(user_id)
    if not user:
        return OrderResult(success=False, error="کاربر پیدا نشد.")

    if user["balance"] < selling_price:
        return OrderResult(success=False, error="موجودی کافی نیست.")

    # بررسی کلید API
    api_key = await db.get_setting("sintel_api")
    if not api_key:
        return OrderResult(success=False, error="API سینتل تنظیم نشده است.")

    # کسر موجودی (با قفل برای جلوگیری از race condition)
    lock_key = f"sintel_order_{user_id}"
    lock = asyncio.Lock()

    # TODO: پیاده‌سازی قفل مناسب برای تراکنش‌های مالی
    if not await db.deduct_balance(user_id, selling_price):
        return OrderResult(success=False, error="خطا در کسر موجودی؛ دوباره تلاش کنید.")

    # ایجاد سفارش
    try:
        client = SintelClient(api_key)
        result = await client.create_order(
            service_id=service_id,
            link=link,
            quantity=quantity,
        )

        # استخراج شناسه سفارش
        provider_order_id = str(result.get("order", ""))

        if not provider_order_id:
            # برگشت وجه در صورت عدم دریافت شناسه
            await db.add_balance(user_id, selling_price)
            return OrderResult(success=False, error="شناسه سفارش دریافت نشد.")

        # ذخیره در دیتابیس
        order_id = await _save_order_to_db(
            user_id=user_id,
            provider_order_id=provider_order_id,
            service_id=service_id,
            link=link,
            quantity=quantity,
            provider_cost=provider_cost,
            selling_price=selling_price,
            status="PENDING",
        )

        log.info(
            "Sintel order created: user=%d, order=%s, provider=%s",
            user_id, order_id, provider_order_id
        )

        return OrderResult(
            success=True,
            order_id=order_id,
            provider_order_id=provider_order_id,
        )

    except SintelError as exc:
        # برگشت وجه در صورت خطا
        await db.add_balance(user_id, selling_price)
        log.warning("Sintel order failed: user=%d, error=%s", user_id, exc)
        return OrderResult(success=False, error=_humanize_error(exc))

    except Exception as exc:
        # برگشت وجه در صورت خطای غیرمنتظره
        await db.add_balance(user_id, selling_price)
        log.exception("Unexpected error creating Sintel order")
        return OrderResult(success=False, error="خطای غیرمنتظره؛ مبلغ برگشت خورد.")


async def _save_order_to_db(
    user_id: int,
    provider_order_id: str,
    service_id: int,
    link: str,
    quantity: int,
    provider_cost: int,
    selling_price: int,
    status: str,
) -> int:
    """ذخیره سفارش در دیتابیس."""
    now = int(time.time())

    async with db._db.execute("""
        INSERT INTO sintel_orders (
            user_id, provider_order_id, service_id, link, quantity,
            provider_cost, selling_price, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        provider_order_id,
        service_id,
        link,
        quantity,
        provider_cost,
        selling_price,
        status,
        now,
        now,
    )) as cur:
        await db._db.commit()
        return int(cur.lastrowid)


async def get_order_status_from_provider(order_id: int) -> OrderStatus:
    """
    بررسی وضعیت سفارش از سینتل.

    Args:
        order_id: شناسه داخلی سفارش

    Returns:
        وضعیت سفارش
    """
    order = await get_sintel_order(order_id)
    if not order:
        return OrderStatus(status="UNKNOWN", error="سفارش پیدا نشد.")

    api_key = await db.get_setting("sintel_api")
    if not api_key:
        return OrderStatus(status=order["status"], error="API سینتل تنظیم نشده.")

    try:
        client = SintelClient(api_key)
        result = await client.get_order_status(int(order["provider_order_id"]))

        provider_status = str(result.get("status", "")).strip()
        mapped_status = ORDER_STATUS_MAP.get(provider_status, order["status"])
        remains = int(result.get("remains") or 0)

        # بروزرسانی وضعیت در دیتابیس
        await _update_order_status(order_id, mapped_status, remains)

        return OrderStatus(status=mapped_status, remains=remains)

    except SintelError as exc:
        log.warning("Failed to get order status: order=%d, error=%s", order_id, exc)
        return OrderStatus(status=order["status"], error=_humanize_error(exc))


async def _update_order_status(order_id: int, status: str, remains: int = 0) -> None:
    """بروزرسانی وضعیت سفارش."""
    await db._db.execute("""
        UPDATE sintel_orders
        SET status=?, remains=?, updated_at=?
        WHERE id=?
    """, (status, remains, int(time.time()), order_id))
    await db._db.commit()


async def get_sintel_order(order_id: int) -> dict[str, Any] | None:
    """دریافت سفارش سینتل."""
    async with db._db.execute(
        "SELECT * FROM sintel_orders WHERE id=?", (order_id,)
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_sintel_orders(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """دریافت سفارشات سینتل کاربر."""
    async with db._db.execute("""
        SELECT * FROM sintel_orders
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT ?
    """, (user_id, limit)) as cur:
        rows = await cur.fetchall()
        return [dict(row) for row in rows]


async def refund_sintel_order(order_id: int, reason: str = "") -> bool:
    """
    بازگشت وجه سفارش سینتل.

    Args:
        order_id: شناسه داخلی سفارش
        reason: دلیل بازگشت

    Returns:
        True در صورت موفقیت
    """
    order = await get_sintel_order(order_id)
    if not order:
        return False

    # فقط سفارشات باز را می‌توان ریفاند کرد
    if order["status"] in FINAL_STATUSES:
        log.info("Cannot refund order %d: status is %s", order_id, order["status"])
        return False

    # بروزرسانی وضعیت
    await _update_order_status(order_id, "REFUNDED")

    # برگشت وجه
    await db.add_balance(order["user_id"], order["selling_price"])

    # اطلاع‌رسانی به کاربر
    try:
        from aiogram import Bot
        # TODO: ارسال پیام به کاربر در صورت نیاز
        log.info("Sintel order %d refunded: %d Toman", order_id, order["selling_price"])
    except Exception as exc:
        log.warning("Failed to notify user about refund: %s", exc)

    return True


async def sync_all_pending_orders(bot=None) -> dict[str, int]:
    """
    همگام‌سازی تمام سفارشات در انتظار.

    Returns:
        تعداد سفارشات در هر وضعیت
    """
    api_key = await db.get_setting("sintel_api")
    if not api_key:
        return {"skipped": 0, "updated": 0, "errors": 0}

    # دریافت سفارشات فعال
    async with db._db.execute("""
        SELECT * FROM sintel_orders
        WHERE status NOT IN ('COMPLETED', 'PARTIAL', 'CANCELED', 'REFUNDED')
        ORDER BY id DESC
        LIMIT 100
    """) as cur:
        orders = [dict(row) for row in await cur.fetchall()]

    stats = {"updated": 0, "errors": 0}

    for order in orders:
        try:
            status = await get_order_status_from_provider(order["id"])
            if status.status != order["status"]:
                stats["updated"] += 1

            # بررسی وضعیت‌های نهایی
            if status.status in FINAL_STATUSES and order["status"] not in FINAL_STATUSES:
                # سفارش بسته شده
                log.info(
                    "Sintel order %s (provider: %s) status: %s -> %s",
                    order["id"], order["provider_order_id"],
                    order["status"], status.status
                )

        except Exception as exc:
            log.warning("Failed to sync order %d: %s", order["id"], exc)
            stats["errors"] += 1

        await asyncio.sleep(0.1)  # جلوگیری از rate limit

    return stats


def calculate_order_price(rate: str, quantity: int) -> int:
    """
    محاسبه قیمت سفارش بر اساس rate سینتل.

    فرمول: rate × quantity ÷ 1000
    """
    try:
        rate_decimal = Decimal(str(rate))
        quantity_decimal = Decimal(str(quantity))
        cost = (rate_decimal * quantity_decimal) / Decimal("1000")
        return int(cost.quantize(Decimal("1")))
    except (ValueError, TypeError, decimal.InvalidOperation):
        return 0


def format_order_status_text(status: str) -> str:
    """تبدیل وضعیت به متن فارسی."""
    status_map = {
        "PENDING": "⏳ در انتظار",
        "PROCESSING": "🔄 در حال انجام",
        "COMPLETED": "✅ تکمیل شده",
        "PARTIAL": "⚠️ تکمیل جزئی",
        "CANCELED": "❌ لغو شده",
        "REFUNDED": "↩️ برگشت داده شده",
    }
    return status_map.get(status, status)


# Import decimal for price calculation
import decimal
