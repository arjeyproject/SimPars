"""هندلر خرید سرویس‌های سینتل (تلگرام و اینستاگرام)."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import texts
from services.sintel import SintelClient, SintelError, _humanize_error
from services.sintel_catalog import (
    SERVICE_CATEGORIES,
    calculate_selling_price,
    get_catalog_by_subcategory,
    get_cached_catalog,
    get_service_by_id,
    sync_catalog_from_provider,
)
from services.sintel_orders import (
    OrderResult,
    calculate_order_price,
    create_sintel_order,
    format_order_status_text,
    get_order_status_from_provider,
    get_sintel_order,
    get_user_sintel_orders,
)
from utils import calc_price, esc, safe_edit

router = Router()
log = logging.getLogger(__name__)

# قفل‌های جلوگیری از کلیک تکراری
_order_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


class SintelStates(StatesGroup):
    """وضعیت‌های ماشین حالت."""
    link = State()
    quantity = State()


def _is_sintel_enabled() -> bool:
    """بررسی فعال بودن سینتل."""
    return True  # TODO: بررسی از تنظیمات


async def _get_profit_percent() -> float:
    """دریافت درصد سود."""
    return max(0.0, await db.get_float("sintel_profit_percent", await db.get_float("profit_percent", 30)))


def _format_service_button(service: dict) -> tuple[str, str, str]:
    """فرمت‌دهی اطلاعات سرویس برای دکمه."""
    name = service.get("name", "نامشخص")[:50]
    rate = service.get("rate", "0")
    min_qty = service.get("min_quantity", 0)

    # نمایش قیمت برای حداقل تعداد
    try:
        price = calculate_order_price(rate, min_qty)
        price_text = f"{price:,}" if price > 0 else "نامشخص"
    except Exception:
        price_text = "—"

    return name, price_text, f"stlg:{service['service_id']}"


async def _check_api_config(call: CallbackQuery) -> bool:
    """بررسی تنظیمات API سینتل."""
    api_key = await db.get_setting("sintel_api")
    if not api_key:
        await call.answer(
            "🔌 سرویس‌های سینتل فعال نیست.\nاز پنل مدیریت API را تنظیم کنید.",
            show_alert=True
        )
        return False
    return True


# ---- منوی اصلی سینتل ----
@router.callback_query(F.data == "sintel")
async def cb_sintel_main(call: CallbackQuery) -> None:
    """منوی اصلی سرویس‌های سینتل."""
    if not await _check_api_config(call):
        return

    api_key = await db.get_setting("sintel_api")
    try:
        client = SintelClient(api_key)
        balance = await client.get_balance()
        balance_text = f"💰 موجودی: <b>{balance:,.0f} تومان</b>"
    except SintelError:
        balance_text = "⚠️ خطا در دریافت موجودی"

    text = (
        "🔌 <b>سرویس‌های سینتل</b>\n\n"
        "سرویس‌های تلگرام و اینستاگرام با بهترین قیمت\n\n"
        f"{balance_text}\n\n"
        "👇 دسته‌بندی مورد نظر را انتخاب کن:"
    )

    await safe_edit(call, text, kb.sintel_main_menu())
    await call.answer()


@router.callback_query(F.data == "sintel_telegram")
async def cb_sintel_telegram_categories(call: CallbackQuery) -> None:
    """دسته‌بندی‌های سرویس‌های تلگرام."""
    if not await _check_api_config(call):
        return

    text = "👥 <b>سرویس‌های تلگرام</b>\n\nدسته‌بندی مورد نظر را انتخاب کن:"

    await safe_edit(call, text, kb.sintel_platform_menu("telegram"))
    await call.answer()


@router.callback_query(F.data == "sintel_instagram")
async def cb_sintel_instagram_categories(call: CallbackQuery) -> None:
    """دسته‌بندی‌های سرویس‌های اینستاگرام."""
    if not await _check_api_config(call):
        return

    text = "📸 <b>سرویس‌های اینستاگرام</b>\n\nدسته‌بندی مورد نظر را انتخاب کن:"

    await safe_edit(call, text, kb.sintel_platform_menu("instagram"))
    await call.answer()


# ---- نمایش سرویس‌های یک زیرشاخه ----
@router.callback_query(F.data.startswith("stsc:"))
async def cb_sintel_subcategory(call: CallbackQuery) -> None:
    """نمایش سرویس‌های یک زیرشاخه."""
    try:
        _, platform, subcategory = call.data.split(":", 2)
    except ValueError:
        await call.answer()
        return

    if not await _check_api_config(call):
        return

    services = await get_catalog_by_subcategory(platform, subcategory)

    if not services:
        # تلاش برای همگام‌سازی
        await call.answer("در حال دریافت سرویس‌ها...", show_alert=True)
        api_key = await db.get_setting("sintel_api")
        result = await sync_catalog_from_provider(api_key)

        if result.get("success"):
            services = await get_catalog_by_subcategory(platform, subcategory)

        if not services:
            await safe_edit(
                call,
                "❌ <b>سرویسی در این دسته موجود نیست.</b>",
                kb.back_to(f"sintel_{platform}")
            )
            return

    # دسته‌بندی‌ها
    subcats = SERVICE_CATEGORIES.get(platform, {}).get("subcategories", {})
    category_info = subcats.get(subcategory, {})
    emoji = category_info.get("emoji", "📊")
    title = category_info.get("title", "سایر")

    text = f"{emoji} <b>{title}</b>\n\n"
    text += f"📦 تعداد سرویس‌ها: {len(services)}\n\n"
    text += "👇 سرویس مورد نظر را انتخاب کن:"

    await safe_edit(call, text, kb.sintel_services_list(services))
    await call.answer()


# ---- انتخاب سرویس و شروع خرید ----
@router.callback_query(F.data.startswith("stlg:"))
async def cb_sintel_service_selected(call: CallbackQuery, state: FSMContext) -> None:
    """انتخاب سرویس و درخواست لینک."""
    try:
        _, service_id = call.data.split(":", 1)
        service_id = int(service_id)
    except (ValueError, IndexError):
        await call.answer()
        return

    if not await _check_api_config(call):
        return

    service = await get_service_by_id(service_id)
    if not service:
        await call.answer("❌ سرویس پیدا نشد.", show_alert=True)
        return

    # ذخیره اطلاعات سرویس در state
    await state.update_data(
        sintel_service_id=service_id,
        sintel_service_name=service.get("name", ""),
        sintel_platform=service.get("platform", ""),
        sintel_rate=service.get("rate", "0"),
        sintel_min=int(service.get("min_quantity", 0)),
        sintel_max=int(service.get("max_quantity", 0)),
    )

    # تعیین متن راهنما بر اساس پلتفرم
    platform = service.get("platform", "")
    if platform == "instagram":
        link_hint = "لینک پست، پروفایل یا ریلز اینستاگرام:\nمثال: https://instagram.com/p/ABC123 یا @username"
    else:
        link_hint = "لینک پست، کانال یا گروه تلگرام:\nمثال: https://t.me/channel/123"

    text = (
        f"🔌 <b>{service.get('name', 'سرویس')}</b>\n\n"
        f"📦 حداقل: <code>{service.get('min_quantity', 0):,}</code>\n"
        f"📦 حداکثر: <code>{service.get('max_quantity', 0):,}</code>\n\n"
        f"📝 {link_hint}"
    )

    await state.set_state(SintelStates.link)
    await safe_edit(call, text, kb.cancel_kb("sintel"))
    await call.answer()


@router.message(SintelStates.link)
async def msg_sintel_link(message: Message, state: FSMContext) -> None:
    """دریافت لینک و درخواست تعداد."""
    data = await state.get_data()

    link = (message.text or "").strip()
    if not link:
        await message.answer("❌ لطفاً لینک معتبر بفرست.")
        return

    # اعتبارسنجی ساده لینک
    platform = data.get("sintel_platform", "")
    if platform == "instagram":
        if not _validate_instagram_link(link):
            await message.answer(
                "❌ لینک اینستاگرام نامعتبر است.\n"
                "مثال: https://instagram.com/p/ABC123 یا @username"
            )
            return
    else:
        if not _validate_telegram_link(link):
            await message.answer(
                "❌ لینک تلگرام نامعتبر است.\n"
                "مثال: https://t.me/channel/123"
            )
            return

    await state.update_data(sintel_link=link)

    min_qty = data.get("sintel_min", 0)
    max_qty = data.get("sintel_max", 0)

    text = (
        f"🔌 <b>{data.get('sintel_service_name', 'سرویس')}</b>\n\n"
        f"✅ لینک: <code>{esc(link)}</code>\n\n"
        f"📦 تعداد مورد نظر را وارد کن:\n"
        f"   حداقل: <code>{min_qty:,}</code>\n"
        f"   حداکثر: <code>{max_qty:,}</code>"
    )

    await state.set_state(SintelStates.quantity)
    await message.answer(text, reply_markup=kb.cancel_kb("sintel"))


def _validate_telegram_link(link: str) -> bool:
    """اعتبارسنجی لینک تلگرام."""
    link = link.lower().strip()
    valid_patterns = [
        "t.me/",
        "telegram.me/",
        "telegram.dog/",
    ]
    return any(pattern in link for pattern in valid_patterns)


def _validate_instagram_link(link: str) -> bool:
    """اعتبارسنجی لینک اینستاگرام."""
    link = link.lower().strip()
    # لینک اینستاگرام یا یوزرنیم
    if link.startswith("@"):
        return len(link) > 1
    valid_patterns = [
        "instagram.com/",
        "instagr.am/",
    ]
    return any(pattern in link for pattern in valid_patterns)


@router.message(SintelStates.quantity)
async def msg_sintel_quantity(message: Message, state: FSMContext) -> None:
    """دریافت تعداد و نمایش پیش‌فاکتور."""
    try:
        quantity = int(message.text.strip().replace(",", ""))
    except ValueError:
        await message.answer("❌ تعداد نامعتبر. لطفاً عدد وارد کن.")
        return

    data = await state.get_data()
    min_qty = data.get("sintel_min", 0)
    max_qty = data.get("sintel_max", 0)

    if quantity < min_qty:
        await message.answer(f"❌ حداقل تعداد: {min_qty:,}")
        return

    if quantity > max_qty:
        await message.answer(f"❌ حداکثر تعداد: {max_qty:,}")
        return

    await state.update_data(sintel_quantity=quantity)

    # محاسبه قیمت
    rate = data.get("sintel_rate", "0")
    provider_cost = calculate_order_price(rate, quantity)
    profit_percent = await _get_profit_percent()
    selling_price = calculate_selling_price(provider_cost, profit_percent)

    # بررسی موجودی کاربر
    user = await db.get_user(message.from_user.id)
    balance = int(user["balance"]) if user else 0

    enough = balance >= selling_price
    note = "✅ موجودی کافی است." if enough else "⚠️ موجودی کافی نیست!"

    text = (
        f"🧾 <b>پیش‌فاکتور</b>\n\n"
        f"🔌 سرویس: <b>{data.get('sintel_service_name', '')}</b>\n"
        f"🔗 لینک: <code>{esc(data.get('sintel_link', ''))}</code>\n"
        f"📦 تعداد: <b>{quantity:,}</b>\n\n"
        f"💰 قیمت: <b>{selling_price:,} تومان</b>\n"
        f"👛 موجودی شما: <b>{balance:,} تومان</b>\n\n"
        f"{note}"
    )

    await state.update_data(
        sintel_provider_cost=provider_cost,
        sintel_selling_price=selling_price,
    )

    await message.answer(
        text,
        reply_markup=kb.sintel_confirm_kb(enough)
    )


# ---- تایید و پرداخت ----
@router.callback_query(F.data == "sintel_buy")
async def cb_sintel_buy(call: CallbackQuery, state: FSMContext) -> None:
    """تایید و خرید."""
    user_id = call.from_user.id
    data = await state.get_data()

    lock = _order_locks[user_id]
    if lock.locked():
        await call.answer("⏳ درخواست قبلی در حال پردازش است.", show_alert=True)
        return

    async with lock:
        result: OrderResult = await create_sintel_order(
            user_id=user_id,
            service_id=data.get("sintel_service_id"),
            link=data.get("sintel_link"),
            quantity=data.get("sintel_quantity"),
            provider_cost=data.get("sintel_provider_cost", 0),
            selling_price=data.get("sintel_selling_price", 0),
        )

    if result.success:
        await call.answer("✅ سفارش با موفقیت ثبت شد!")
        await safe_edit(
            call,
            f"🎉 <b>سفارش با موفقیت ثبت شد!</b>\n\n"
            f"🆔 کد سفارش: <code>#{result.order_id}</code>\n"
            f"📦 تعداد: <code>{data.get('sintel_quantity'):,}</code>\n"
            f"💰 مبلغ: <b>{data.get('sintel_selling_price'):,} تومان</b>\n\n"
            f"⏳ وضعیت سفارش به‌صورت خودکار بروزرسانی می‌شود.",
            kb.back_to("sintel_orders")
        )
    else:
        await call.answer(result.error or "❌ خطا در ثبت سفارش", show_alert=True)

    await state.clear()


@router.callback_query(F.data == "sintel_wallet")
async def cb_sintel_wallet(call: CallbackQuery, state: FSMContext) -> None:
    """انتقال به کیف پول."""
    await state.clear()
    await safe_edit(call, "💰 برای شارژ کیف پول از دکمه زیر استفاده کن:",
                    kb.markup([
                        [kb.btn("💰 شارژ کیف پول", "wallet", style="success")],
                        [kb.btn("🏠 منوی اصلی", "home", style="danger")]
                    ]))
    await call.answer()


# ---- پیگیری سفارشات ----
@router.callback_query(F.data == "sintel_orders")
async def cb_sintel_orders(call: CallbackQuery) -> None:
    """نمایش سفارشات کاربر."""
    orders = await get_user_sintel_orders(call.from_user.id, 10)

    if not orders:
        await safe_edit(
            call,
            "📭 <b>هنوز سفارشی ثبت نکردید!</b>",
            kb.markup([
                [kb.btn("🔌 خرید سرویس جدید", "sintel", style="success")],
                [kb.btn("🏠 منوی اصلی", "home", style="danger")]
            ])
        )
        await call.answer()
        return

    text = "📦 <b>سفارشات سینتل شما</b>\n\n"

    for order in orders:
        service = await get_service_by_id(order["service_id"])
        service_name = service.get("name", "نامشخص") if service else "نامشخص"
        status_text = format_order_status_text(order["status"])

        text += (
            f"━━━━━━━━━━━━━━\n"
            f"🆔 <code>#{order['id']}</code>\n"
            f"🔌 {service_name[:30]}\n"
            f"📦 {order['quantity']:,} واحد\n"
            f"💰 {order['selling_price']:,} تومان\n"
            f"📊 وضعیت: {status_text}\n"
        )

    text += "━━━━━━━━━━━━━━"

    await safe_edit(call, text, kb.sintel_orders_kb())
    await call.answer()


@router.callback_query(F.data.startswith("stch:"))
async def cb_sintel_check_order(call: CallbackQuery) -> None:
    """بررسی وضعیت سفارش."""
    try:
        order_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer()
        return

    status = await get_order_status_from_provider(order_id)
    order = await get_sintel_order(order_id)

    if not order:
        await call.answer("❌ سفارش پیدا نشد.", show_alert=True)
        return

    service = await get_service_by_id(order["service_id"])
    service_name = service.get("name", "نامشخص") if service else "نامشخص"

    text = (
        f"🔄 <b>بررسی وضعیت سفارش</b>\n\n"
        f"🆔 کد: <code>#{order_id}</code>\n"
        f"🔌 سرویس: {service_name[:30]}\n"
        f"📦 تعداد: {order['quantity']:,}\n\n"
        f"📊 وضعیت: <b>{format_order_status_text(status.status)}</b>"
    )

    if status.remains > 0:
        text += f"\n⏳ باقیمانده: {status.remains:,}"

    if status.error:
        text += f"\n⚠️ {status.error}"

    await safe_edit(call, text, kb.sintel_order_detail_kb(order_id, status.status))
    await call.answer()
