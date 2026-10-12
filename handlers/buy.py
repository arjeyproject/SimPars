"""Virtual-number storefront handlers."""
from __future__ import annotations

import asyncio
import logging
import math
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
from services.payments import notify_admins
from utils import calc_price, country_title, esc, safe_edit, service_title

router = Router()
log = logging.getLogger(__name__)
PAGE_SIZE = 10
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _pricing() -> tuple[float, float]:
    return await db.get_float("rate", 1000), max(0.0, await db.get_float("profit_percent", 30))


async def _loading(call: CallbackQuery, frames: list[str], pause: float = 0.16) -> None:
    for frame in frames:
        try:
            await call.message.edit_text(frame)
            await asyncio.sleep(pause)
        except Exception:
            return


@router.callback_query(F.data == "buy")
async def cb_buy(call: CallbackQuery) -> None:
    if not await db.get_setting("fivesim_api") or not await sales_allowed():
        await call.answer(texts.SALES_DISABLED, show_alert=True)
        return
    await safe_edit(call, texts.CHOOSE_SERVICE, kb.services_kb())
    await call.answer()


@router.callback_query(F.data.startswith("srv:"))
async def cb_service(call: CallbackQuery) -> None:
    try:
        _, product, page_raw = call.data.split(":")
        page = int(page_raw)
    except ValueError:
        await call.answer()
        return
    if not await sales_allowed():
        await call.answer(texts.SALES_DISABLED, show_alert=True)
        return
    await call.answer("⏳ در حال دریافت اطلاعات...")
    await _loading(call, ["🌍 <b>اتصال به سرور کشورها</b> ▓░░░", "📡 <b>دریافت موجودی زنده</b> ▓▓░░", "💰 <b>محاسبه قیمت‌ها</b> ▓▓▓░", "✨ <b>مرتب‌سازی فهرست</b> ▓▓▓▓"], 0.12)
    try:
        prices = await fivesim.get_product_prices(product)
    except FiveSimError as exc:
        await safe_edit(call, humanize(exc), kb.back_to("buy"))
        return
    if not prices:
        await safe_edit(call, texts.NO_NUMBERS, kb.back_to("buy"))
        return
    countries = await fivesim.countries_safe()
    rate, profit = await _pricing()
    items = sorted(((country, calc_price(cost, rate, profit)) for country, (_, cost, _) in prices.items()), key=lambda item: item[1])
    pages = max(1, math.ceil(len(items) / PAGE_SIZE))
    page = min(max(0, page), pages - 1)
    chunk = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    buttons = [(country, f"{country_title(country, countries)}\n💰 {price:,} تومان") for country, price in chunk]
    text = texts.CHOOSE_COUNTRY.format(service=f"<b>{service_title(product)}</b>", count=len(items), page=page + 1, pages=pages)
    await safe_edit(call, text, kb.countries_kb(product, buttons, page, pages))


@router.callback_query(F.data.startswith("cn:"))
async def cb_country(call: CallbackQuery) -> None:
    try:
        _, product, country = call.data.split(":")
    except ValueError:
        await call.answer()
        return
    if not await sales_allowed():
        await call.answer(texts.SALES_DISABLED, show_alert=True)
        return
    try:
        prices = await fivesim.get_product_prices(product)
    except FiveSimError as exc:
        await call.answer(humanize(exc), show_alert=True)
        return
    info = prices.get(country)
    if not info:
        await call.answer("😕 موجودی این کشور تمام شده، کشور دیگری انتخاب کن.", show_alert=True)
        return
    _, cost, count = info
    rate, profit = await _pricing()
    price = calc_price(cost, rate, profit)
    user = await db.get_user(call.from_user.id)
    balance = user["balance"] if user else 0
    countries = await fivesim.countries_safe()
    await safe_edit(call, texts.CONFIRM.format(service=service_title(product), country=country_title(country, countries), count=count, price=price, balance=balance, note=texts.NOTE_OK if balance >= price else texts.NOTE_LOW), kb.confirm_kb(product, country, balance >= price))
    await call.answer()


@router.callback_query(F.data.startswith("ok:"))
async def cb_purchase(call: CallbackQuery) -> None:
    try:
        _, product, country = call.data.split(":")
    except ValueError:
        await call.answer()
        return
    if not await sales_allowed():
        await call.answer(texts.SALES_DISABLED, show_alert=True)
        return
    user_id = call.from_user.id
    lock = _locks[user_id]
    if lock.locked():
        await call.answer("⏳ درخواست قبلی در حال پردازش است...", show_alert=True)
        return
    async with lock:
        token = await db.get_setting("fivesim_api")
        if not token or not await sales_allowed():
            await call.answer(texts.SALES_DISABLED, show_alert=True)
            return
        await call.answer("⏳ در حال رزرو شماره...")
        await _loading(call, ["🛒 <b>آماده‌سازی سفارش</b> ▓░░░", "🔐 <b>بررسی کیف پول</b> ▓▓░░", "📡 <b>رزرو شماره از تامین‌کننده</b> ▓▓▓░"], 0.14)
        try:
            prices = await fivesim.get_product_prices(product, use_cache=False)
        except FiveSimError as exc:
            await safe_edit(call, humanize(exc), kb.back_to(f"srv:{product}:0"))
            return
        info = prices.get(country)
        if not info:
            await safe_edit(call, texts.NO_NUMBERS, kb.back_to(f"srv:{product}:0"))
            return
        operator, cost, _ = info
        rate, profit = await _pricing()
        price = calc_price(cost, rate, profit)
        if not await db.deduct_balance(user_id, price):
            user = await db.get_user(user_id)
            await safe_edit(call, texts.INSUFFICIENT.format(price=price, balance=user["balance"] if user else 0), kb.markup([[kb.btn("💳 شارژ کیف پول", "wallet")], [kb.btn("🏠 منوی اصلی", "home")]]))
            return
        try:
            data = await FiveSimClient(token).buy(country, operator, product)
        except FiveSimError as exc:
            await db.add_balance(user_id, price)
            log.warning("buy failed %s/%s/%s: %s", country, operator, product, exc)
            if "balance" in str(exc).lower() or "rating" in str(exc).lower():
                await notify_admins(call.bot, f"⚠️ <b>هشدار:</b> خرید ناموفق به دلیل موجودی/امتیاز پنل 5Sim!\n<code>{esc(exc)}</code>")
            await safe_edit(call, f"❌ <b>خرید انجام نشد</b>\n\n{humanize(exc)}\n\n💰 مبلغ به کیف پولت برگشت.", kb.back_to(f"srv:{product}:0"))
            return
        phone = str(data.get("phone") or "")
        order_id = await db.create_order(user_id, int(data["id"]), phone, product, country, str(data.get("operator") or operator), price, ORDER_LIFETIME)
    countries = await fivesim.countries_safe()
    await safe_edit(call, texts.ORDER_CREATED.format(order_id=order_id, service=service_title(product), country=country_title(country, countries), phone=esc(phone), price=price, minutes=ORDER_LIFETIME // 60), kb.order_kb(order_id))


async def _own_order(call: CallbackQuery):
    try:
        order_id = int(call.data.split(":")[1])
    except (ValueError, IndexError):
        return None
    order = await db.get_order(order_id)
    return order if order and order["user_id"] == call.from_user.id else None


@router.callback_query(F.data.startswith("chk:"))
async def cb_check(call: CallbackQuery) -> None:
    order = await _own_order(call)
    if not order:
        await call.answer("❌ سفارش پیدا نشد.", show_alert=True)
        return
    if order["status"] in ("CANCELED", "TIMEOUT"):
        await call.answer("↩️ این سفارش لغو شده و مبلغش برگشت خورده.", show_alert=True)
        return
    try:
        result = await sync_order(call.bot, order, notify=False)
    except FiveSimError as exc:
        await call.answer(humanize(exc), show_alert=True)
        return
    status = result["status"]
    if status in ("RECEIVED", "FINISHED") and (result.get("code") or result.get("text")):
        await call.answer("📩 کد تأیید دریافت شد!")
        markup = kb.order_received_kb(order["id"]) if status == "RECEIVED" else kb.back_main()
        await safe_edit(call, code_message(order, result.get("code") or "", result.get("text") or ""), markup)
    elif status == "TIMEOUT":
        await call.answer("↩️ سفارش بسته شد و مبلغ برگشت خورد.", show_alert=True)
        reason = texts.REASON_BANNED if result.get("reason") == "banned" else texts.REASON_TIMEOUT
        await safe_edit(call, texts.REFUNDED.format(order_id=order["id"], phone=esc(order["phone"]), price=order["price"], reason=reason), kb.back_main())
    else:
        await call.answer(texts.WAITING_CODE, show_alert=True)


@router.callback_query(F.data.startswith("cnl:"))
async def cb_cancel(call: CallbackQuery) -> None:
    order = await _own_order(call)
    if not order:
        await call.answer("❌ سفارش پیدا نشد.", show_alert=True)
        return
    if order["status"] != "PENDING":
        await call.answer("⚠️ این سفارش قابل لغو نیست.", show_alert=True)
        return
    try:
        await FiveSimClient(await db.get_setting("fivesim_api")).cancel(order["fivesim_id"])
    except FiveSimError as exc:
        await call.answer(humanize(exc), show_alert=True)
        return
    if await refund(call.bot, order, "CANCELED", texts.REASON_USER, notify=False):
        await call.answer("✅ سفارش لغو و مبلغ برگشت داده شد.")
        await safe_edit(call, texts.REFUNDED.format(order_id=order["id"], phone=esc(order["phone"]), price=order["price"], reason=texts.REASON_USER), kb.markup([[kb.btn("🛒 خرید شماره جدید", "buy")], [kb.btn("🏠 منوی اصلی", "home")]]))
    else:
        await call.answer("ℹ️ وضعیت این سفارش قبلاً تغییر کرده.", show_alert=True)


@router.callback_query(F.data.startswith("fin:"))
async def cb_finish(call: CallbackQuery) -> None:
    order = await _own_order(call)
    if not order:
        await call.answer("❌ سفارش پیدا نشد.", show_alert=True)
        return
    if order["status"] == "RECEIVED":
        try:
            await FiveSimClient(await db.get_setting("fivesim_api")).finish(order["fivesim_id"])
        except FiveSimError:
            pass
        await db.transition_order(order["id"], ("RECEIVED",), "FINISHED")
    await call.answer("🏁 سفارش تکمیل شد")
    await safe_edit(call, texts.ORDER_FINISHED.format(order_id=order["id"]), kb.markup([[kb.btn("🛒 خرید شماره جدید", "buy")], [kb.btn("🏠 منوی اصلی", "home")]]))
