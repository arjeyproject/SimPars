"""Virtual-number storefront with direct payment fallback."""
from __future__ import annotations
import asyncio, logging, math
from collections import defaultdict
from aiogram import F, Router
from aiogram.types import CallbackQuery
import database as db
import keyboards as kb
import texts
from config import ORDER_LIFETIME
from services import fivesim
from services.fivesim import FiveSimClient, FiveSimError, humanize
from services.market import sales_allowed
from services.orders import code_message, refund, sync_order
from services.purchase_checkout import create_invoice
from services import zarinpal
from utils import calc_price, country_title, esc, phone_ltr, safe_edit, service_title
router = Router(); log = logging.getLogger(__name__); PAGE_SIZE = 10; _locks = defaultdict(asyncio.Lock)
async def _pricing(): return await db.get_float("rate", 1000), max(0.0, await db.get_float("profit_percent", 30))
async def _loading(call, frames, pause=.12):
    for frame in frames:
        try: await call.message.edit_text(frame); await asyncio.sleep(pause)
        except Exception: return
async def _show_countries(call: CallbackQuery, product: str, page: int = 0, category: str = "economic"):
    try: prices = await fivesim.get_product_prices(product)
    except FiveSimError as exc: await safe_edit(call, humanize(exc), kb.back_to("buy")); return
    if not prices: await safe_edit(call, texts.NO_NUMBERS, kb.back_to("buy")); return
    countries = await fivesim.countries_safe(); rate, profit = await _pricing()
    items = [(country, calc_price(cost, rate, profit)) for country, (_, cost, _) in prices.items()]
    items.sort(key=lambda item: item[1]); pages = max(1, math.ceil(len(items) / PAGE_SIZE)); page = min(max(0, page), pages - 1); chunk = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    buttons = [(country_title(c, countries), f"{price:,} تومان", f"cn:{product}:{c}:{category}") for c, price in chunk]
    title = "خرید اقتصادی" if category == "economic" else "خرید اختصاصی"; text = f"<b>{service_title(product)}</b>\n\n{title}\nکشور را انتخاب کن.\nصفحه {page + 1} از {pages}"
    await safe_edit(call, text, kb.countries_kb(product, buttons, page, pages))
@router.callback_query(F.data.startswith("srv:"))
async def cb_service(call: CallbackQuery):
    try: parts = call.data.split(":"); product = parts[1]; page = int(parts[2]); category = parts[3] if len(parts) > 3 else "economic"
    except (ValueError, IndexError): await call.answer(); return
    if not await sales_allowed(): await call.answer("فروش موقتاً غیرفعال است؛ نرخ را در پنل بررسی کن.", show_alert=True); return
    await call.answer("در حال دریافت کشورها و قیمت‌ها..."); await _loading(call, ["اتصال به کشورها ▓░░░", "دریافت موجودی ▓▓░░", "مرتب‌سازی قیمت‌ها ▓▓▓░", "آماده‌سازی ▓▓▓▓"]); await _show_countries(call, product, page, category)
@router.callback_query(F.data.startswith("cn:"))
async def cb_country(call: CallbackQuery):
    try: parts = call.data.split(":"); product, country = parts[1], parts[2]; category = parts[3] if len(parts) > 3 else "economic"
    except (ValueError, IndexError): await call.answer(); return
    try: options = await fivesim.get_product_options(product, use_cache=False)
    except FiveSimError as exc: await call.answer(humanize(exc), show_alert=True); return
    values = options.get(country, [])
    if not values: await call.answer("موجودی این کشور تمام شده است.", show_alert=True); return
    rate, profit = await _pricing(); chosen = min(values, key=lambda item: item[1]) if category == "economic" else max(values, key=lambda item: item[1])
    operator, cost, count = chosen; price = calc_price(cost, rate, profit); user = await db.get_user(call.from_user.id); balance = user["balance"] if user else 0; countries = await fivesim.countries_safe()
    text = texts.CONFIRM.format(service=service_title(product), country=country_title(country, countries), count=count, price=price, balance=balance, note=texts.NOTE_OK if balance >= price else "⚠️ موجودی کافی نیست؛ همین مبلغ را مستقیم پرداخت کن.")
    await safe_edit(call, text, kb.confirm_kb(product, country, operator, True)); await call.answer()
@router.callback_query(F.data.startswith("ok:"))
async def cb_purchase(call: CallbackQuery):
    try: _, product, country, operator = call.data.split(":", 3)
    except ValueError: await call.answer(); return
    if not await sales_allowed(): await call.answer("فروش موقتاً غیرفعال است.", show_alert=True); return
    lock = _locks[call.from_user.id]
    if lock.locked(): await call.answer("درخواست قبلی در حال پردازش است.", show_alert=True); return
    async with lock:
        token = await db.get_setting("fivesim_api")
        if not token: await call.answer("اتصال فروشگاه در پنل مدیریت تنظیم نشده است.", show_alert=True); return
        await call.answer("در حال آماده‌سازی فاکتور..."); await _loading(call, ["آماده‌سازی فاکتور ▓░░░", "بررسی قیمت دقیق ▓▓░░", "ساخت لینک پرداخت ▓▓▓░"])
        try: options = await fivesim.get_product_options(product, use_cache=False)
        except FiveSimError as exc: await safe_edit(call, humanize(exc), kb.back_to(f"srv:{product}:0")); return
        match = next((x for x in options.get(country, []) if x[0] == operator), None) or (min(options.get(country, []), key=lambda x: x[1]) if options.get(country) else None)
        if not match: await safe_edit(call, texts.NO_NUMBERS, kb.back_to(f"srv:{product}:0")); return
        operator, cost, _ = match; rate, profit = await _pricing(); price = calc_price(cost, rate, profit); user = await db.get_user(call.from_user.id); balance = user["balance"] if user else 0
        if int(balance) < int(price):
            try: authority, invoice_price = await create_invoice(call.from_user.id, {"product": product, "country": country, "operator": operator})
            except Exception as exc: log.exception("direct invoice creation failed"); await safe_edit(call, f"❌ <b>ساخت لینک پرداخت ناموفق بود</b>\n\n{esc(str(exc))}", kb.back_to(f"srv:{product}:0")); return
            invoice = ("🧾 <b>فاکتور خرید شماره</b>\n\n" f"📲 سرویس: <b>{service_title(product)}</b>\n" f"🌍 کشور: <b>{country_title(country, await fivesim.countries_safe())}</b>\n" f"💰 مبلغ دقیق: <b>{invoice_price:,} تومان</b>\n" f"👛 موجودی کیف پول: <b>{int(balance):,} تومان</b>\n\n" "⚠️ موجودی کافی نیست. برای پرداخت دقیق همین مبلغ روی دکمه زیر بزن.\n" "✅ بعد از پرداخت، تایید و دریافت شماره خودکار انجام می‌شود.")
            await safe_edit(call, invoice, kb.markup([[kb.btn("💳 ورود به درگاه پرداخت", url=zarinpal.payment_url(authority), style="success")], [kb.btn("✅ پرداخت کردم، بررسی شود", f"vfy:{authority}", style="success")], [kb.btn("🏠 منوی اصلی", "home", style="danger")]])); return
        if not await db.deduct_balance(call.from_user.id, price): await safe_edit(call, "⚠️ موجودی تغییر کرد؛ دوباره تلاش کن.", kb.back_to(f"srv:{product}:0")); return
        try: data = await FiveSimClient(token).buy(country, operator, product)
        except FiveSimError as exc:
            await db.add_balance(call.from_user.id, price); log.warning("buy failed: %s", exc); await safe_edit(call, f"❌ <b>خرید انجام نشد</b>\n\n{humanize(exc)}\n\nمبلغ برگشت خورد.", kb.back_to(f"srv:{product}:0")); return
        phone = str(data.get("phone") or ""); order_id = await db.create_order(call.from_user.id, int(data["id"]), phone, product, country, str(data.get("operator") or operator), price, ORDER_LIFETIME)
    countries = await fivesim.countries_safe(); await safe_edit(call, texts.ORDER_CREATED.format(order_id=order_id, service=service_title(product), country=country_title(country, countries), phone=phone_ltr(phone), price=price, minutes=ORDER_LIFETIME // 60), kb.order_kb(order_id))
async def _own_order(call):
    try: order = await db.get_order(int(call.data.split(":")[1]))
    except (ValueError, IndexError): return None
    return order if order and order["user_id"] == call.from_user.id else None
@router.callback_query(F.data.startswith("chk:"))
async def cb_check(call: CallbackQuery):
    order = await _own_order(call)
    if not order: await call.answer("سفارش پیدا نشد.", show_alert=True); return
    if order["status"] in ("CANCELED", "TIMEOUT"): await call.answer("مبلغ قبلاً برگشت خورده.", show_alert=True); return
    try: result = await sync_order(call.bot, order, notify=False)
    except FiveSimError as exc: await call.answer(humanize(exc), show_alert=True); return
    if result["status"] in ("RECEIVED", "FINISHED") and (result.get("code") or result.get("text")):
        await call.answer("کد تأیید دریافت شد!"); await safe_edit(call, code_message(order, result.get("code") or "", result.get("text") or ""), kb.order_received_kb(order["id"]) if result["status"] == "RECEIVED" else kb.back_main())
    elif result["status"] == "TIMEOUT":
        await call.answer("سفارش بسته شد و مبلغ برگشت خورد.", show_alert=True); reason = texts.REASON_BANNED if result.get("reason") == "banned" else texts.REASON_TIMEOUT; await safe_edit(call, texts.REFUNDED.format(order_id=order["id"], phone=phone_ltr(order["phone"]), price=order["price"], reason=reason), kb.back_main())
    else: await call.answer(texts.WAITING_CODE, show_alert=True)
@router.callback_query(F.data.startswith("cnl:"))
async def cb_cancel(call: CallbackQuery):
    order = await _own_order(call)
    if not order: await call.answer("سفارش پیدا نشد.", show_alert=True); return
    if order["status"] != "PENDING": await call.answer("این سفارش قابل لغو نیست.", show_alert=True); return
    try: await FiveSimClient(await db.get_setting("fivesim_api")).cancel(order["fivesim_id"])
    except FiveSimError as exc: await call.answer(humanize(exc), show_alert=True); return
    if await refund(call.bot, order, "CANCELED", texts.REASON_USER, notify=False):
        await call.answer("لغو شد و مبلغ برگشت خورد."); await safe_edit(call, texts.REFUNDED.format(order_id=order["id"], phone=phone_ltr(order["phone"]), price=order["price"], reason=texts.REASON_USER), kb.markup([[kb.btn("خرید شماره جدید", "buy")], [kb.btn("🏠 منوی اصلی", "home")]]))
@router.callback_query(F.data.startswith("fin:"))
async def cb_finish(call: CallbackQuery):
    order = await _own_order(call)
    if not order: await call.answer("سفارش پیدا نشد.", show_alert=True); return
    if order["status"] == "RECEIVED":
        try: await FiveSimClient(await db.get_setting("fivesim_api")).finish(order["fivesim_id"])
        except FiveSimError: pass
        await db.transition_order(order["id"], ("RECEIVED",), "FINISHED")
    await call.answer("سفارش تکمیل شد"); await safe_edit(call, texts.ORDER_FINISHED.format(order_id=order["id"]), kb.markup([[kb.btn("خرید شماره جدید", "buy")], [kb.btn("🏠 منوی اصلی", "home")]]))
