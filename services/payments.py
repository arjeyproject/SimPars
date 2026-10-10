"""SimPars - پردازش پرداخت‌های زیبال"""
from __future__ import annotations

import logging

from aiogram import Bot

import database as db
import keyboards as kb
import texts
from config import ADMIN_IDS, BASE_URL, BOT_USERNAME
from services import zibal
from utils import esc

log = logging.getLogger(__name__)


async def get_merchant() -> str:
    if await db.get_setting("zibal_sandbox") == "1":
        return zibal.SANDBOX_MERCHANT
    return (await db.get_setting("zibal_merchant")).strip()


async def get_callback_url() -> str:
    custom = (await db.get_setting("zibal_callback")).strip()
    if custom:
        return custom
    if BASE_URL:
        return f"{BASE_URL}/zibal/callback"
    return f"https://t.me/{BOT_USERNAME}"


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:  # noqa: BLE001
            pass


async def process_payment(bot: Bot, track_id: str, notify_user: bool = True) -> tuple[bool, str]:
    """تایید پرداخت و شارژ کیف پول (فقط یک‌بار)."""
    payment = await db.get_payment(track_id)
    if not payment:
        return False, "❌ تراکنش پیدا نشد."
    if payment["status"] == "paid":
        return True, "✅ این تراکنش قبلاً تایید و کیف پولت شارژ شده."

    merchant = await get_merchant()
    if not merchant:
        return False, "⛔️ درگاه پرداخت تنظیم نشده است."
    try:
        data = await zibal.verify_payment(merchant, track_id)
    except zibal.ZibalError as exc:
        return False, f"⚠️ {exc}"

    result = data.get("result")
    if result not in (100, 201):
        return False, "❌ پرداخت هنوز انجام نشده یا ناموفق بوده. اگه پول کم شده، حداکثر تا ۷۲ ساعت برمی‌گرده."
    paid_amount = data.get("amount")
    if paid_amount is not None and int(paid_amount) != int(payment["amount"]) * 10:
        log.warning("amount mismatch for %s: %s", track_id, paid_amount)
        return False, "⚠️ مغایرت در مبلغ تراکنش! لطفاً با پشتیبانی تماس بگیر."

    ref = str(data.get("refNumber") or track_id)
    if not await db.mark_payment_paid(track_id, ref):
        return True, "✅ این تراکنش قبلاً تایید و کیف پولت شارژ شده."

    user_id, amount = payment["user_id"], payment["amount"]
    await db.add_balance(user_id, amount)
    user = await db.get_user(user_id)
    message = texts.PAYMENT_SUCCESS.format(amount=amount, ref=esc(ref), balance=user["balance"] if user else amount)

    if notify_user:
        try:
            await bot.send_message(user_id, message, reply_markup=kb.back_main())
        except Exception:  # noqa: BLE001
            pass

    # پاداش دعوت
    if user and user["referrer_id"]:
        percent = await db.get_float("referral_percent", 0)
        bonus = int(amount * percent / 100)
        if bonus > 0:
            await db.add_balance(user["referrer_id"], bonus)
            try:
                await bot.send_message(
                    user["referrer_id"],
                    f"🎁 <b>تبریک!</b> یکی از دوستانت کیف پولش رو شارژ کرد و "
                    f"<b>{bonus:,} تومان</b> هدیه به حسابت اضافه شد 🎉",
                )
            except Exception:  # noqa: BLE001
                pass

    await notify_admins(
        bot,
        f"💳 <b>پرداخت جدید</b>\n\n👤 کاربر: <code>{user_id}</code>\n"
        f"💵 مبلغ: <b>{amount:,} تومان</b>\n🧾 مرجع: <code>{esc(ref)}</code>",
    )
    return True, message
