"""Direct payment context and automatic number delivery after gateway verification."""
from __future__ import annotations

import json
import logging
import time

from aiogram import Bot

import database as db
import texts
from config import ORDER_LIFETIME
from services import coupons, fivesim, zarinpal
from services.fivesim import FiveSimClient, FiveSimError
from utils import calc_price, country_title, esc, service_title

log = logging.getLogger(__name__)
_table_ready = False


async def _ensure_context_table() -> None:
    global _table_ready
    if _table_ready:
        return
    await db._db.execute("CREATE TABLE IF NOT EXISTS payment_context(track_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    await db._db.commit()
    _table_ready = True


async def get_context(track_id: str):
    await _ensure_context_table()
    async with db._db.execute("SELECT payload FROM payment_context WHERE track_id=?", (str(track_id),)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


async def _pricing() -> tuple[float, float]:
    return await db.get_float("rate", 1000), max(0.0, await db.get_float("profit_percent", 30))


async def resolve(payload: dict) -> tuple[int, str, str]:
    options = await fivesim.get_product_options(payload["product"], use_cache=False)
    match = next((item for item in options.get(payload["country"], []) if item[0] == payload["operator"]), None)
    if not match:
        raise FiveSimError("این شماره دیگر موجود نیست")
    operator, cost, _ = match
    rate, profit = await _pricing()
    base = calc_price(cost, rate, profit)
    percent = 0
    code = (payload.get("coupon") or "").strip().upper()
    if code:
        valid, _, percent = await coupons.validate(code)
        if not valid:
            code, percent = "", 0
    return max(1, int(round(base * (100 - percent) / 100))), operator, code


async def create_invoice(user_id: int, payload: dict) -> tuple[str, int]:
    """فاکتور اتوماتیک: مبلغ دقیق شماره را در زرین‌پال ثبت و context خرید را ذخیره می‌کند."""
    from services.payments import get_callback_url, get_merchant

    price, _, code = await resolve(payload)
    merchant = await get_merchant()
    if not merchant:
        raise zarinpal.ZarinpalError("درگاه زرین‌پال تنظیم نشده است")
    user = await db.get_user(user_id)
    mobile = user["contact_phone"] if user and "contact_phone" in user.keys() else None
    authority = await zarinpal.create_payment(
        merchant,
        price * 10,
        await get_callback_url(),
        description=f"خرید شماره {payload['product']} - کاربر {user_id}",
        order_id=f"buy-{user_id}-{int(time.time())}",
        mobile=mobile,
    )
    stored = {**payload, "coupon": code, "price": price}
    await _ensure_context_table()
    # context قبل از payment ذخیره می‌شود تا callback هرگز آن را شارژ کیف پول فرض نکند.
    await db._db.execute("INSERT OR REPLACE INTO payment_context(track_id, payload) VALUES(?, ?)", (authority, json.dumps(stored, ensure_ascii=False)))
    await db._db.commit()
    await db.create_payment(user_id, price, authority)
    return authority, price


async def finish_paid_purchase(bot: Bot, payment, payload: dict, ref: str) -> tuple[bool, str, int | None]:
    """پرداخت اتوماتیک: بعد از verify، شماره را از 5Sim می‌خرد؛ در خطا مبلغ به کیف پول برمی‌گردد."""
    user_id = int(payment["user_id"])
    paid = int(payment["amount"])
    refund_note = f"مبلغ <b>{paid:,} تومان</b> به کیف پولت برگشت خورد و می‌تونی شماره دیگه‌ای بخری."
    operator = payload.get("operator")
    coupon_code = (payload.get("coupon") or "").strip().upper()
    try:
        # قیمت پرداخت‌شده مبنا است؛ فقط موجود بودن اپراتور بررسی می‌شود تا تغییر نرخ باعث رد سفارش نشود.
        _, operator, _ = await resolve({**payload, "coupon": ""})
    except Exception as exc:  # noqa: BLE001
        await db.add_balance(user_id, paid)
        log.warning("paid purchase resolve failed: %s", exc)
        return False, f"پرداخت تایید شد اما این شماره دیگر موجود نیست.\n{refund_note}", None
    token = await db.get_setting("fivesim_api")
    if not token:
        await db.add_balance(user_id, paid)
        return False, f"پرداخت تایید شد اما فروشگاه موقتاً در دسترس نیست.\n{refund_note}", None
    try:
        data = await FiveSimClient(token).buy(payload["country"], operator, payload["product"])
        fivesim_id = int(data["id"])
    except Exception as exc:  # noqa: BLE001
        await db.add_balance(user_id, paid)
        log.warning("paid purchase failed: %s", exc)
        detail = esc(str(exc)) if isinstance(exc, FiveSimError) else ""
        return False, f"پرداخت تایید شد اما رزرو شماره انجام نشد.\n{refund_note}\n\n{detail}".strip(), None
    order_id = await db.create_order(user_id, fivesim_id, str(data.get("phone") or ""), payload["product"], payload["country"], str(data.get("operator") or operator), paid, ORDER_LIFETIME)
    if coupon_code:
        try:
            await coupons.consume(coupon_code)
        except Exception:  # noqa: BLE001
            log.warning("coupon consume failed: %s", coupon_code)
    countries = await fivesim.countries_safe()
    message = texts.ORDER_CREATED.format(
        order_id=order_id,
        service=service_title(payload["product"]),
        country=country_title(payload["country"], countries),
        phone=esc(str(data.get("phone") or "")),
        price=paid,
        minutes=ORDER_LIFETIME // 60,
    )
    return True, message, order_id
