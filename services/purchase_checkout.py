"""Direct purchase: server-side quote, Telegram invoice, ZarinPal request and exactly-once delivery."""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass
from aiogram import Bot
import config
import database as db
import keyboards as kb
import texts
from config import ORDER_LIFETIME
from services import coupons, fivesim, zarinpal
from services.fivesim import FiveSimClient, FiveSimError
from utils import calc_price, country_title, esc, service_title
log = logging.getLogger(__name__)
_invoice_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
REQUIRED_KEYS = ("product", "country", "operator")

@dataclass(frozen=True)
class Quote:
    base_price: int
    discount_percent: int
    final_price: int
    operator: str
    coupon: str

async def get_context(track_id: str):
    payment = await db.get_payment(track_id)
    raw = payment["context"] if payment else None
    if not raw:
        async with db._db.execute("SELECT payload FROM payment_context WHERE track_id=?", (str(track_id),)) as cur:
            row = await cur.fetchone()
        raw = row[0] if row else None
    if not raw: return None
    try: return json.loads(raw)
    except json.JSONDecodeError: return None

async def _pricing() -> tuple[float, float]: return await db.get_float("rate", 1000), max(0.0, await db.get_float("profit_percent", 30))
def _check_payload(payload: dict) -> None:
    if not isinstance(payload, dict) or any(not str(payload.get(key) or "").strip() for key in REQUIRED_KEYS): raise FiveSimError("اطلاعات شماره انتخاب‌شده ناقص است")
async def quote(payload: dict) -> Quote:
    _check_payload(payload)
    options = await fivesim.get_product_options(payload["product"], use_cache=False)
    match = next((item for item in options.get(payload["country"], []) if item[0] == payload["operator"]), None)
    if not match: raise FiveSimError("این شماره دیگر موجود نیست")
    operator, cost, _ = match; rate, profit = await _pricing(); base = calc_price(cost, rate, profit); percent = 0; code = (payload.get("coupon") or "").strip().upper()
    if code:
        valid, _, percent = await coupons.validate(code)
        if not valid: code, percent = "", 0
    percent = max(0, min(100, int(percent))); final = max(1000, int(round(base * (100 - percent) / 100)))
    return Quote(base_price=int(base), discount_percent=percent, final_price=final, operator=operator, coupon=code)
async def resolve(payload: dict) -> tuple[int, str, str]:
    q = await quote(payload); return q.final_price, q.operator, q.coupon
def _fingerprint(user_id: int, payload: dict, q: Quote) -> str:
    raw = f"{user_id}|{payload['product']}|{payload['country']}|{q.operator}|{q.coupon}|{q.final_price}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
def _new_invoice_id() -> str: return f"SP{time.strftime('%y%m%d')}{secrets.token_hex(4).upper()}"

async def create_invoice(user_id: int, payload: dict):
    from services.payments import get_callback_url, get_merchant, is_sandbox
    async with _invoice_locks[int(user_id)]:
        q = await quote(payload); fingerprint = _fingerprint(user_id, payload, q)
        existing = await db.find_reusable_invoice(user_id, fingerprint, int(time.time()) - config.INVOICE_REUSE_SECONDS)
        if existing: return existing
        merchant = await get_merchant()
        if not merchant: raise zarinpal.ZarinpalError("درگاه زرین‌پال تنظیم نشده است")
        invoice_id = _new_invoice_id(); callback = await get_callback_url(invoice_id)
        context = {"product": payload["product"], "country": payload["country"], "operator": q.operator, "coupon": q.coupon, "price": q.final_price}
        await db.create_invoice_row(user_id, "purchase", invoice_id, q.final_price, zarinpal.toman_to_rial(q.final_price), q.base_price, q.discount_percent, q.coupon, json.dumps(context, ensure_ascii=False), fingerprint)
        try:
            authority = await zarinpal.create_payment(merchant, q.final_price, callback, description=f"خرید شماره مجازی SimPars - فاکتور {invoice_id}", order_id=invoice_id, sandbox=await is_sandbox())
        except Exception as exc:
            await db.fail_invoice_request(invoice_id, str(exc)); raise
        if not await db.attach_authority(invoice_id, authority): raise zarinpal.ZarinpalError("ثبت فاکتور ناموفق بود")
        return await db.get_payment_by_invoice(invoice_id)

async def invoice_text(payment, countries: dict | None = None) -> str:
    ctx = json.loads(payment["context"] or "{}"); base = int(payment["base_price"] or payment["amount"]); percent = int(payment["discount_percent"] or 0); final = int(payment["amount"])
    discount = f"🎁 تخفیف ({esc(payment['coupon'])}): <b>{percent}٪ = {base - final:,} تومان</b>\n" if percent else ""
    return ("🧾 <b>فاکتور خرید شماره مجازی</b>\n\n" f"🔢 شماره فاکتور: <code>{esc(payment['invoice_id'])}</code>\n" f"📲 سرویس: <b>{service_title(ctx.get('product', ''))}</b>\n" f"🌍 کشور: <b>{country_title(ctx.get('country', ''), countries)}</b>\n" f"📡 اپراتور: <b>{esc(ctx.get('operator', ''))}</b>\n" f"💵 قیمت محصول: <b>{base:,} تومان</b>\n{discount}" f"💰 مبلغ قابل پرداخت: <b>{final:,} تومان</b>\n\n" f"⏳ اعتبار لینک: حدود {max(1, config.INVOICE_REUSE_SECONDS // 60)} دقیقه\n" "✅ بعد از پرداخت موفق و تایید سرور، شماره خودکار و فقط یک‌بار تحویل می‌شود.")
def invoice_kb(payment, sandbox: bool = False):
    return kb.markup([[kb.btn("💳 پرداخت با زرین‌پال", url=zarinpal.payment_url(payment["track_id"], sandbox=sandbox), style="success")], [kb.btn("✅ پرداخت کردم، بررسی شود", f"vfy:{payment['track_id']}", style="success")], [kb.btn("🏠 منوی اصلی", "home", style="danger")]])
def failed_kb(invoice_id: str):
    return kb.markup([[kb.btn("🔁 تلاش مجدد تحویل شماره", f"rdl:{invoice_id}", style="success")], [kb.btn("💰 انتقال مبلغ به کیف پول", f"rfd:{invoice_id}", style="primary")], [kb.btn("🏠 منوی اصلی", "home", style="danger")]])
async def _order_message(order) -> str:
    countries = await fivesim.countries_safe()
    return texts.ORDER_CREATED.format(order_id=order["id"], service=service_title(order["product"]), country=country_title(order["country"], countries), phone=esc(order["phone"]), price=order["price"], minutes=ORDER_LIFETIME // 60)

async def deliver(bot: Bot, track_id: str, from_statuses: tuple = ("awaiting",)):
    if not await db.claim_delivery(track_id, from_statuses):
        payment = await db.get_payment(track_id); return await delivery_status_message(bot, payment, notify_user=False, resume=False)
    payment = await db.get_payment(track_id); user_id, paid, invoice_id = int(payment["user_id"]), int(payment["amount"]), payment["invoice_id"] or track_id; payload = await get_context(track_id)
    fail_note = "💳 پرداختت ثبت و محفوظ است و نیازی به پرداخت دوباره نیست.\nمی‌توانی دوباره تلاش کنی یا مبلغ را به کیف پول منتقل کنی."
    try:
        if not payload: raise FiveSimError("اطلاعات سفارش پیدا نشد")
        q = await quote(payload); token = await db.get_setting("fivesim_api")
        if not token: raise FiveSimError("فروشگاه موقتاً در دسترس نیست")
        data = await FiveSimClient(token).buy(payload["country"], q.operator, payload["product"])
    except FiveSimError as exc:
        log.warning("delivery failed for %s: %s", track_id, exc); await db.fail_delivery(track_id, str(exc), "failed")
        return False, f"⚠️ <b>تحویل شماره انجام نشد</b>\n\n{esc(fivesim.humanize(exc))}\n\n{fail_note}", failed_kb(invoice_id)
    except Exception as exc:
        log.exception("delivery crashed for %s", track_id); await db.fail_delivery(track_id, f"unexpected: {exc}", "review")
        return False, "⚠️ تحویل شماره با خطای غیرمنتظره روبه‌رو شد. پرداختت محفوظ است و پشتیبانی بررسی می‌کند.", kb.back_main()
    try:
        order_id = await db.create_order(user_id, int(data["id"]), str(data.get("phone") or ""), payload["product"], payload["country"], str(data.get("operator") or q.operator), paid, ORDER_LIFETIME); await db.finish_delivery(track_id, order_id)
    except Exception as exc:
        log.exception("order save failed after provider purchase for %s", track_id); await db.fail_delivery(track_id, f"bought fivesim_id={data.get('id')} phone={data.get('phone')} but save failed: {exc}", "review")
        return False, f"⚠️ شماره رزرو شد اما ثبت سفارش خطا داد. پشتیبانی با شناسه <code>{esc(invoice_id)}</code> پیگیری می‌کند.", kb.back_main()
    if q.coupon:
        try: await coupons.consume(q.coupon)
        except Exception: log.warning("coupon consume failed: %s", q.coupon)
    order = await db.get_order(order_id); return True, await _order_message(order), kb.order_kb(order_id)

async def delivery_status_message(bot: Bot, payment, notify_user: bool = False, resume: bool = True):
    status = payment["delivery_status"]
    if status == "awaiting" and resume:
        ok, message, markup = await deliver(bot, payment["track_id"])
        if notify_user:
            try: await bot.send_message(payment["user_id"], message, reply_markup=markup)
            except Exception: pass
        return ok, message, markup
    if status == "delivered" and payment["order_id"]:
        order = await db.get_order(payment["order_id"])
        if order: return True, "✅ این پرداخت قبلاً تایید و شماره تحویل شده است.\n\n" + await _order_message(order), kb.order_kb(order["id"]) if order["status"] == "PENDING" else kb.back_main()
    if status in ("processing", "awaiting"): return True, "⏳ پرداخت تایید شده و تحویل شماره در حال انجام است.", kb.back_main()
    if status == "failed": return False, "⚠️ پرداخت تایید شده ولی تحویل شماره انجام نشد. پرداختت محفوظ است.", failed_kb(payment["invoice_id"] or payment["track_id"])
    if status == "refunded": return True, f"💰 مبلغ این فاکتور ({int(payment['amount']):,} تومان) قبلاً به کیف پولت منتقل شده است.", kb.back_main()
    if status == "review": return True, "🛠 پرداخت تایید شده و تحویل در حال بررسی پشتیبانی است. نیازی به پرداخت دوباره نیست.", kb.back_main()
    return True, "✅ این تراکنش قبلاً تایید شده است.", kb.back_main()

async def finish_paid_purchase(bot: Bot, payment, payload: dict, ref: str):
    ok, message, _ = await deliver(bot, payment["track_id"]); return ok, message
