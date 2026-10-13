"""SimPars - پردازش پرداخت‌های زرین‌پال."""
from __future__ import annotations
import asyncio
import logging
import time
from aiogram import Bot
import database as db
import keyboards as kb
import texts
from config import ADMIN_IDS, BASE_URL, BOT_USERNAME
from services import zarinpal
from utils import esc
log = logging.getLogger(__name__)
_payment_locks: dict[str, asyncio.Lock] = {}

async def get_merchant() -> str:
    if await db.get_setting("zibal_sandbox") == "1": return zarinpal.SANDBOX_MERCHANT
    return (await db.get_setting("zibal_merchant")).strip()

async def get_callback_url() -> str:
    custom = (await db.get_setting("zibal_callback")).strip()
    if custom: return custom
    if BASE_URL: return f"{BASE_URL}/zarinpal/callback"
    return f"https://t.me/{BOT_USERNAME}"

async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try: await bot.send_message(admin_id, text)
        except Exception: pass

async def _verify(merchant: str, payment, track_id: str):
    try: data = await zarinpal.verify_payment(merchant, track_id, int(payment["amount"]) * 10)
    except zarinpal.ZarinpalError as exc: return None, f"⚠️ {exc}"
    result = data.get("data") if isinstance(data.get("data"), dict) else {}
    code = result.get("code", data.get("code"))
    if code not in (100, 101): return None, "❌ پرداخت انجام نشده یا ناموفق بوده. اگر پول کم شده، با پشتیبانی تماس بگیر."
    paid_amount = result.get("amount")
    if paid_amount is not None and int(paid_amount) != int(payment["amount"]) * 10:
        log.warning("amount mismatch for %s: %s", track_id, paid_amount)
        return None, "⚠️ مغایرت در مبلغ تراکنش! لطفاً با پشتیبانی تماس بگیر."
    return result, ""

async def process_payment(bot: Bot, track_id: str, notify_user: bool = True) -> tuple[bool, str]:
    lock = _payment_locks.setdefault(str(track_id), asyncio.Lock())
    async with lock:
        try:
            return await _process_payment(bot, track_id, notify_user)
        finally:
            if not lock.locked():
                _payment_locks.pop(str(track_id), None)

async def _process_payment(bot: Bot, track_id: str, notify_user: bool = True) -> tuple[bool, str]:
    payment = await db.get_payment(track_id)
    if not payment: return False, "❌ تراکنش پیدا نشد."
    if payment["status"] == "paid": return True, "✅ این تراکنش قبلاً تایید شده است."
    merchant = await get_merchant()
    if not merchant: return False, "⛔️ درگاه زرین‌پال تنظیم نشده است."
    from services.purchase_checkout import finish_paid_purchase, get_context
    purchase = await get_context(track_id)
    result, error = await _verify(merchant, payment, track_id)
    if result is None: return False, error
    ref = str(result.get("ref_id") or result.get("card_pan") or track_id)
    if not await db.mark_payment_paid(track_id, ref): return True, "✅ این تراکنش قبلاً تایید شده است."
    if purchase:
        try:
            ok, message = await finish_paid_purchase(bot, payment, purchase, ref)
        except Exception:  # noqa: BLE001
            log.exception("finish_paid_purchase crashed for %s", track_id)
            await db.add_balance(payment["user_id"], int(payment["amount"]))
            ok, message = False, f"پرداخت تایید شد اما ثبت سفارش با خطا مواجه شد؛ مبلغ <b>{int(payment['amount']):,} تومان</b> به کیف پولت اضافه شد."
        if notify_user:
            try: await bot.send_message(payment["user_id"], ("✅ پرداخت تایید شد.\n\n" + message), reply_markup=kb.back_main() if ok else kb.markup([[kb.btn("💰 کیف پول", "wallet")], [kb.btn("🏠 منوی اصلی", "home")]]))
            except Exception: pass
        status = "خرید مستقیم تایید شد" if ok else "پرداخت شد ولی شماره تحویل نشد (به کیف پول برگشت)"
        await notify_admins(bot, f"💳 <b>{status}</b>\n\n👤 کاربر: <code>{payment['user_id']}</code>\n💵 مبلغ: <b>{payment['amount']:,} تومان</b>\n🧾 مرجع: <code>{esc(ref)}</code>")
        return ok, message
    user_id, amount = payment["user_id"], payment["amount"]
    await db.add_balance(user_id, amount)
    user = await db.get_user(user_id)
    message = texts.PAYMENT_SUCCESS.format(amount=amount, ref=esc(ref), balance=user["balance"] if user else amount)
    if notify_user:
        try: await bot.send_message(user_id, message, reply_markup=kb.back_main())
        except Exception: pass
    if user and user["referrer_id"]:
        percent = await db.get_float("referral_percent", 0); bonus = int(amount * percent / 100)
        if bonus > 0:
            await db.add_balance(user["referrer_id"], bonus)
            try: await bot.send_message(user["referrer_id"], f"🎁 <b>تبریک!</b> از شارژ دوستت <b>{bonus:,} تومان</b> هدیه گرفتی 🎉")
            except Exception: pass
    await notify_admins(bot, f"💳 <b>پرداخت زرین‌پال</b>\n\n👤 کاربر: <code>{user_id}</code>\n💵 مبلغ: <b>{amount:,} تومان</b>\n🧾 مرجع: <code>{esc(ref)}</code>")
    return True, message

async def reconcile_pending_payments(bot: Bot, min_age: int = 120, max_age: int = 1800, limit: int = 10) -> int:
    """پرداخت‌هایی که کاربر بعد از پرداخت به سایت/ربات برنگشته را خودکار verify می‌کند.

    بدون این، زرین‌پال تراکنش verify نشده را برمی‌گرداند و فروش از دست می‌رود.
    """
    if not await get_merchant(): return 0
    now = int(time.time())
    async with db._db.execute("SELECT track_id FROM payments WHERE status='pending' AND created_at BETWEEN ? AND ? ORDER BY id DESC LIMIT ?", (now - max_age, now - min_age, int(limit))) as cur:
        rows = await cur.fetchall()
    confirmed = 0
    for row in rows:
        try:
            ok, _ = await process_payment(bot, row["track_id"], notify_user=True)
            if ok: confirmed += 1
        except Exception:  # noqa: BLE001
            log.exception("reconcile %s failed", row["track_id"])
        await asyncio.sleep(0.5)
    if confirmed: log.info("reconciled %s abandoned payments", confirmed)
    return confirmed
