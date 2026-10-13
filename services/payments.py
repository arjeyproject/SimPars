"""SimPars - پردازش پرداخت‌های زرین‌پال (Callback، Verify، شارژ کیف پول و تحویل خرید مستقیم)."""
from __future__ import annotations
import asyncio
import logging
import time
from urllib.parse import urlencode, urlsplit
from aiogram import Bot
import config
import database as db
import keyboards as kb
import texts
from services import zarinpal
from utils import esc
log = logging.getLogger(__name__)
_payment_locks: dict[str, asyncio.Lock] = {}
CALLBACK_PATH = "/callback/zarinpal"
LEGACY_CALLBACK_PATH = "/zarinpal/callback"


async def is_sandbox() -> bool:
    if config.ZARINPAL_SANDBOX in ("0", "1"):
        return config.ZARINPAL_SANDBOX == "1"
    return await db.get_setting("zibal_sandbox") == "1"


async def get_merchant() -> str:
    if await is_sandbox(): return zarinpal.SANDBOX_MERCHANT
    return (config.ZARINPAL_MERCHANT_ID or await db.get_setting("zibal_merchant")).strip()


def _canonical_base_url() -> str:
    return (config.BASE_URL or "").strip().rstrip("/")


def _same_origin(a: str, b: str) -> bool:
    try:
        pa, pb = urlsplit(a), urlsplit(b)
    except ValueError:
        return False
    return (pa.scheme.lower(), pa.netloc.lower()) == (pb.scheme.lower(), pb.netloc.lower())


async def get_callback_url(invoice_id: str | None = None) -> str:
    """Return one canonical HTTPS callback, optionally tagged with our invoice id.

    Priority: ZARINPAL_CALLBACK_URL (.env) -> saved admin value -> BASE_URL + /callback/zarinpal.
    Anything on another origin than BASE_URL is ignored, because ZarinPal rejects (-14)
    callbacks outside the registered domain.
    """
    base = _canonical_base_url()
    if not base.lower().startswith("https://"):
        raise zarinpal.ZarinpalError("BASE_URL باید دقیقاً با https:// و دامنه ثبت‌شده زرین‌پال تنظیم شود")
    url = f"{base}{CALLBACK_PATH}"
    for candidate, source in ((config.ZARINPAL_CALLBACK_URL, "env"), ((await db.get_setting("zibal_callback")).strip().rstrip("/"), "admin")):
        if not candidate:
            continue
        if candidate.lower().startswith("https://") and _same_origin(candidate, base):
            url = candidate
            break
        log.warning("Ignoring %s ZarinPal callback %s; canonical origin is %s", source, candidate, base)
    if invoice_id:
        url += ("&" if "?" in url else "?") + urlencode({"oid": invoice_id})
    return url


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in config.ADMIN_IDS:
        try: await bot.send_message(admin_id, text)
        except Exception: pass


async def _safe_send(bot: Bot, user_id: int, text: str, markup=None) -> None:
    try: await bot.send_message(user_id, text, reply_markup=markup)
    except Exception as exc: log.warning("notify %s failed: %s", user_id, exc)


def _expected_amount_ok(payment) -> bool:
    stored_rial = payment["amount_rial"]
    return stored_rial is None or int(stored_rial) == int(payment["amount"]) * 10


async def _verify(payment, track_id: str):
    merchant = await get_merchant()
    if not merchant: return None, "⛔️ درگاه زرین‌پال تنظیم نشده است."
    if not _expected_amount_ok(payment):
        log.error("stored amount mismatch for %s: amount=%s rial=%s", track_id, payment["amount"], payment["amount_rial"])
        return None, "⚠️ مغایرت در مبلغ ثبت‌شده تراکنش! لطفاً با پشتیبانی تماس بگیر."
    try:
        result = await zarinpal.verify_payment(merchant, track_id, int(payment["amount"]), sandbox=await is_sandbox())
    except zarinpal.ZarinpalError as exc:
        return None, f"⚠️ {exc}. اگر مبلغ کم شده نگران نباش؛ چند دقیقه بعد دوباره «بررسی پرداخت» را بزن."
    if not result.ok:
        log.info("verify rejected for %s: code=%s", track_id, result.code)
        return None, f"❌ پرداخت تایید نشد ({esc(result.message)}). اگر مبلغ از حسابت کم شده، طی ۷۲ ساعت توسط بانک برمی‌گردد."
    return result, ""


async def process_payment(bot: Bot, track_id: str, notify_user: bool = True) -> tuple[bool, str]:
    ok, message, _ = await process_payment_full(bot, track_id, notify_user)
    return ok, message


async def process_payment_full(bot: Bot, track_id: str, notify_user: bool = True):
    """Verify a transaction exactly once and deliver its goods exactly once.

    Returns (ok, message, reply_markup). Safe against duplicate/concurrent callbacks:
    an in-process lock per authority plus atomic conditional UPDATEs in SQLite.
    """
    track_id = str(track_id or "").strip()
    if not zarinpal.valid_authority(track_id): return False, "❌ شناسه تراکنش نامعتبر است.", None
    lock = _payment_locks.setdefault(track_id, asyncio.Lock())
    async with lock:
        try:
            return await _process_payment(bot, track_id, notify_user)
        finally:
            if not lock.locked(): _payment_locks.pop(track_id, None)


async def _process_payment(bot: Bot, track_id: str, notify_user: bool):
    from services import purchase_checkout as pc
    payment = await db.get_payment(track_id)
    if not payment: return False, "❌ تراکنش پیدا نشد.", None
    if payment["status"] == "paid":
        if payment["kind"] == "purchase":
            return await pc.delivery_status_message(bot, payment, notify_user=notify_user)
        return True, "✅ این تراکنش قبلاً تایید شده است.", kb.back_main()
    if payment["status"] not in ("pending", "canceled"):
        return False, "❌ این فاکتور قابل پرداخت نیست؛ از داخل ربات فاکتور جدید بساز.", None
    result, error = await _verify(payment, track_id)
    if result is None: return False, error, None
    ref = result.ref_id or result.card_pan or track_id
    if not await db.mark_payment_paid(track_id, ref, result.code):
        payment = await db.get_payment(track_id)
        if payment and payment["kind"] == "purchase":
            return await pc.delivery_status_message(bot, payment, notify_user=False)
        return True, "✅ این تراکنش قبلاً تایید شده است.", kb.back_main()
    payment = await db.get_payment(track_id)
    if payment["kind"] == "purchase":
        ok, message, markup = await pc.deliver(bot, track_id)
        if notify_user: await _safe_send(bot, payment["user_id"], "✅ پرداخت تایید شد.\n\n" + message, markup)
        status = "خرید مستقیم تایید و تحویل شد" if ok else "پرداخت تایید شد ولی تحویل شماره انجام نشد (قابل تلاش مجدد)"
        await notify_admins(bot, f"💳 <b>{status}</b>\n\n🧾 فاکتور: <code>{esc(payment['invoice_id'] or '-')}</code>\n👤 کاربر: <code>{payment['user_id']}</code>\n💵 مبلغ: <b>{payment['amount']:,} تومان</b>\n🔖 مرجع: <code>{esc(ref)}</code>")
        return ok, message, markup
    return await _credit_wallet(bot, payment, ref, notify_user)


async def _credit_wallet(bot: Bot, payment, ref: str, notify_user: bool):
    user_id, amount = payment["user_id"], int(payment["amount"])
    await db.add_balance(user_id, amount)
    user = await db.get_user(user_id)
    message = texts.PAYMENT_SUCCESS.format(amount=amount, ref=esc(ref), balance=user["balance"] if user else amount)
    if notify_user: await _safe_send(bot, user_id, message, kb.back_main())
    if user and user["referrer_id"]:
        percent = await db.get_float("referral_percent", 0); bonus = int(amount * percent / 100)
        if bonus > 0:
            await db.add_balance(user["referrer_id"], bonus)
            await _safe_send(bot, user["referrer_id"], f"🎁 <b>تبریک!</b> از شارژ دوستت <b>{bonus:,} تومان</b> هدیه گرفتی 🎉")
    await notify_admins(bot, f"💳 <b>پرداخت زرین‌پال</b>\n\n👤 کاربر: <code>{user_id}</code>\n💵 مبلغ: <b>{amount:,} تومان</b>\n🧾 مرجع: <code>{esc(ref)}</code>")
    return True, message, kb.back_main()


async def handle_callback(bot: Bot, authority: str, status: str, invoice_id: str = "") -> tuple[bool, str]:
    """Logic behind GET /callback/zarinpal. Status=OK alone never marks anything as paid."""
    authority, status, invoice_id = (authority or "").strip(), (status or "").strip().upper(), (invoice_id or "").strip()
    if not zarinpal.valid_authority(authority): return False, "اطلاعات بازگشتی درگاه نامعتبر است."
    payment = await db.get_payment(authority)
    if not payment: return False, "تراکنش پیدا نشد. از داخل ربات فاکتور جدید بساز."
    if invoice_id and payment["invoice_id"] and invoice_id != payment["invoice_id"]:
        log.warning("callback invoice mismatch: authority=%s oid=%s stored=%s", authority, invoice_id, payment["invoice_id"])
        return False, "اطلاعات بازگشتی با فاکتور ثبت‌شده مطابقت ندارد."
    if status != "OK":
        if payment["status"] == "paid": return True, "این تراکنش قبلاً پرداخت و تایید شده است."
        if await db.mark_payment_canceled(authority):
            await _safe_send(bot, payment["user_id"], f"❌ <b>پرداخت فاکتور {esc(payment['invoice_id'] or '')} لغو شد یا ناموفق بود.</b>\n\nهیچ مبلغی ثبت نشد. برای خرید دوباره از منوی ربات اقدام کن.", kb.back_main())
        return False, "پرداخت لغو شد یا ناموفق بود."
    ok, message, _ = await process_payment_full(bot, authority, notify_user=True)
    return ok, message


async def reconcile_pending_payments(bot: Bot, min_age: int = 120, max_age: int = 1800, limit: int = 10) -> int:
    """Background safety net: verify abandoned callbacks and resume interrupted deliveries."""
    from services import purchase_checkout as pc
    confirmed = 0
    if await get_merchant():
        now = int(time.time())
        for row in await db.payments_to_reconcile(now - max_age, now - min_age, limit):
            try:
                ok, _, _ = await process_payment_full(bot, row["track_id"], notify_user=True)
                if ok: confirmed += 1
            except Exception: log.exception("reconcile %s failed", row["track_id"])
            await asyncio.sleep(0.5)
    for row in await db.paid_awaiting_delivery(limit):
        try:
            ok, message, markup = await pc.deliver(bot, row["track_id"])
            await _safe_send(bot, row["user_id"], message, markup)
        except Exception: log.exception("resume delivery %s failed", row["track_id"])
    for row in await db.stale_deliveries(int(time.time()) - 600, limit):
        if await db.fail_delivery(row["track_id"], "interrupted while processing", status="review"):
            await notify_admins(bot, f"⚠️ <b>تحویل نیمه‌کاره نیاز به بررسی دستی دارد</b>\n\n🧾 فاکتور: <code>{esc(row['invoice_id'] or '-')}</code>\n👤 کاربر: <code>{row['user_id']}</code>\n💵 مبلغ: <b>{row['amount']:,} تومان</b>\nپرداخت تایید شده؛ قبل از بازگشت وجه، سفارش‌های 5Sim را چک کن.")
    return confirmed
