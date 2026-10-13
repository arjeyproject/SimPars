"""SimPars - پردازش، تایید و بازیابی خودکار پرداخت‌های زرین‌پال."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

import database as db
import keyboards as kb
import texts
from config import ADMIN_IDS, BASE_URL
from services import zarinpal
from utils import esc

log = logging.getLogger(__name__)
CALLBACK_PATH = "/zarinpal/callback"
_payment_locks: dict[str, asyncio.Lock] = {}
_lock_refs: dict[str, int] = {}


@dataclass
class PaymentResult:
    ok: bool
    message: str
    markup: InlineKeyboardMarkup | None = None


def _wallet_markup() -> InlineKeyboardMarkup:
    return kb.markup([[kb.btn("💰 کیف پول", "wallet")], [kb.btn("🏠 منوی اصلی", "home")]])


def _after_topup_markup() -> InlineKeyboardMarkup:
    return kb.markup([[kb.btn("🛒 خرید شماره مجازی", "buy")], [kb.btn("🏠 منوی اصلی", "home")]])


async def get_merchant() -> str:
    if await db.get_setting("zibal_sandbox") == "1":
        return zarinpal.SANDBOX_MERCHANT
    return (await db.get_setting("zibal_merchant")).strip()


async def is_sandbox() -> bool:
    return (await db.get_setting("zibal_sandbox")) == "1"


def _canonical_base_url() -> str:
    return (BASE_URL or "").strip().rstrip("/")


async def get_callback_url() -> str:
    """آدرس Callback یکتا: همیشه {origin}/zarinpal/callback.

    قبلاً اگر مقدار ذخیره‌شده در پنل فقط دامنه (بدون مسیر) یا مسیر قدیمی
    /zibal/callback بود، زرین‌پال کاربر را به مسیری می‌فرستاد که verify در آن
    انجام نمی‌شد و پرداخت خودکار تایید نمی‌شد. حالا مسیر همیشه اصلاح می‌شود.
    """
    base = _canonical_base_url()
    saved = (await db.get_setting("zibal_callback")).strip().rstrip("/")
    origin = base
    if saved:
        try:
            parts = urlsplit(saved)
            saved_origin = f"{parts.scheme.lower()}://{parts.netloc.lower()}" if parts.scheme and parts.netloc else ""
            if not base and saved_origin:
                origin = saved_origin
            elif saved_origin and base and saved_origin != base.lower():
                log.warning("Ignoring stale ZarinPal callback %s; canonical origin is %s", saved, base)
        except ValueError:
            log.warning("Ignoring invalid saved ZarinPal callback: %s", saved)
    if not origin.lower().startswith("https://"):
        log.error("BASE_URL must be an https:// origin registered in ZarinPal (current: %r)", origin)
    return f"{origin}{CALLBACK_PATH}"


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:  # noqa: BLE001
            pass


async def _verify(merchant: str, payment, authority: str):
    amount_rial = int(payment["amount"]) * 10
    try:
        response = await zarinpal.verify_payment(merchant, authority, amount_rial)
    except zarinpal.ZarinpalError as exc:
        return None, f"⚠️ {exc}"
    code = zarinpal.response_code(response)
    if code not in (zarinpal.SUCCESS, zarinpal.ALREADY_VERIFIED):
        log.info("verify %s -> %s", authority, code)
        if code == -51:
            return None, "❌ پرداخت انجام نشده یا ناموفق بوده. اگر مبلغ از حسابت کم شده، طی ۷۲ ساعت توسط بانک برمی‌گردد."
        return None, f"❌ {zarinpal.message_for(code)}"
    result = response.get("data") if isinstance(response.get("data"), dict) else {}
    return result, ""


async def process_payment(bot: Bot, track_id: str, notify_user: bool = True) -> tuple[bool, str]:
    result = await process_payment_result(bot, track_id, notify_user)
    return result.ok, result.message


async def process_payment_result(bot: Bot, track_id: str, notify_user: bool = True) -> PaymentResult:
    key = str(track_id)
    lock = _payment_locks.setdefault(key, asyncio.Lock())
    _lock_refs[key] = _lock_refs.get(key, 0) + 1
    try:
        async with lock:
            return await _process_payment(bot, key, notify_user)
    finally:
        _lock_refs[key] -= 1
        if _lock_refs[key] <= 0:
            _lock_refs.pop(key, None)
            _payment_locks.pop(key, None)


async def _process_payment(bot: Bot, track_id: str, notify_user: bool, skip_inquiry: bool = False) -> PaymentResult:
    payment = await db.get_payment(track_id)
    if not payment:
        return PaymentResult(False, "❌ تراکنش پیدا نشد.")
    if payment["status"] == "paid":
        return PaymentResult(True, "✅ این تراکنش قبلاً تایید شده است.", kb.back_main())
    merchant = await get_merchant()
    if not merchant:
        return PaymentResult(False, "⛔️ درگاه زرین‌پال تنظیم نشده است.")

    if not skip_inquiry:
        # استعلام فقط برای تصمیم‌گیری است؛ تایید نهایی همیشه با verify انجام می‌شود.
        status = await zarinpal.inquiry_status(merchant, track_id)
        if status == "IN_BANK":
            return PaymentResult(False, "⏳ پرداخت هنوز در درگاه در حال انجام است. بعد از پایان پرداخت دوباره بررسی کن.")
        if status in ("FAILED", "REVERSED"):
            return PaymentResult(False, "❌ این پرداخت ناموفق یا برگشت خورده است. برای پرداخت، فاکتور جدید بساز.")

    result, error = await _verify(merchant, payment, track_id)
    if result is None:
        return PaymentResult(False, error)
    ref = str(result.get("ref_id") or result.get("card_pan") or track_id)
    if not await db.mark_payment_paid(track_id, ref):
        return PaymentResult(True, "✅ این تراکنش قبلاً تایید شده است.", kb.back_main())

    from services.purchase_checkout import finish_paid_purchase, get_context
    purchase = await get_context(track_id)
    if purchase:
        order_id = None
        try:
            ok, message, order_id = await finish_paid_purchase(bot, payment, purchase, ref)
        except Exception:  # noqa: BLE001
            log.exception("finish_paid_purchase crashed for %s", track_id)
            await db.add_balance(payment["user_id"], int(payment["amount"]))
            ok, message = False, f"پرداخت تایید شد اما ثبت سفارش با خطا مواجه شد؛ مبلغ <b>{int(payment['amount']):,} تومان</b> به کیف پولت اضافه شد."
        markup = kb.order_kb(order_id) if ok and order_id else _wallet_markup()
        full = f"✅ پرداخت تایید شد.\n🧾 کد پیگیری: <code>{esc(ref)}</code>\n\n{message}"
        if notify_user:
            try:
                await bot.send_message(payment["user_id"], full, reply_markup=markup)
            except Exception:  # noqa: BLE001
                pass
        status = "خرید مستقیم تایید و شماره تحویل شد" if ok else "پرداخت شد ولی شماره تحویل نشد (به کیف پول برگشت)"
        await notify_admins(bot, f"💳 <b>{status}</b>\n\n👤 کاربر: <code>{payment['user_id']}</code>\n💵 مبلغ: <b>{payment['amount']:,} تومان</b>\n🧾 مرجع: <code>{esc(ref)}</code>")
        return PaymentResult(ok, full, markup)

    user_id, amount = payment["user_id"], int(payment["amount"])
    await db.add_balance(user_id, amount)
    user = await db.get_user(user_id)
    message = texts.PAYMENT_SUCCESS.format(amount=amount, ref=esc(ref), balance=user["balance"] if user else amount)
    if notify_user:
        try:
            await bot.send_message(user_id, message, reply_markup=_after_topup_markup())
        except Exception:  # noqa: BLE001
            pass
    if user and user["referrer_id"]:
        percent = await db.get_float("referral_percent", 0)
        bonus = int(amount * percent / 100)
        if bonus > 0:
            await db.add_balance(user["referrer_id"], bonus)
            try:
                await bot.send_message(user["referrer_id"], f"🎁 <b>تبریک!</b> از شارژ دوستت <b>{bonus:,} تومان</b> هدیه گرفتی 🎉")
            except Exception:  # noqa: BLE001
                pass
    await notify_admins(bot, f"💳 <b>شارژ کیف پول (زرین‌پال)</b>\n\n👤 کاربر: <code>{user_id}</code>\n💵 مبلغ: <b>{amount:,} تومان</b>\n🧾 مرجع: <code>{esc(ref)}</code>")
    return PaymentResult(True, message, _after_topup_markup())


async def reconcile_pending_payments(bot: Bot, min_age: int = 60, max_age: int = 3600, limit: int = 15) -> int:
    """پرداخت خودکار: اگر کاربر بعد از پرداخت به Callback برنگشت، اینجا تایید می‌شود."""
    merchant = await get_merchant()
    if not merchant:
        return 0
    confirmed = 0
    seen: set[str] = set()

    # ۱) تراکنش‌هایی که زرین‌پال می‌گوید پرداخت شده‌اند ولی هنوز verify نشده‌اند.
    for authority in await zarinpal.unverified_authorities(merchant):
        payment = await db.get_payment(authority)
        if not payment or payment["status"] != "pending":
            continue
        seen.add(authority)
        try:
            result = await process_payment_result(bot, authority, notify_user=True)
            confirmed += int(result.ok)
        except Exception:  # noqa: BLE001
            log.exception("reconcile unverified %s failed", authority)
        await asyncio.sleep(0.5)

    # ۲) فاکتورهای در انتظار اخیر (استعلام + verify).
    now = int(time.time())
    async with db._db.execute(
        "SELECT track_id FROM payments WHERE status='pending' AND created_at BETWEEN ? AND ? ORDER BY id DESC LIMIT ?",
        (now - max_age, now - min_age, int(limit)),
    ) as cur:
        rows = await cur.fetchall()
    for row in rows:
        authority = row["track_id"]
        if authority in seen:
            continue
        try:
            result = await process_payment_result(bot, authority, notify_user=True)
            confirmed += int(result.ok)
        except Exception:  # noqa: BLE001
            log.exception("reconcile %s failed", authority)
        await asyncio.sleep(0.5)
    if confirmed:
        log.info("reconciled %s ZarinPal payment(s)", confirmed)
    return confirmed
