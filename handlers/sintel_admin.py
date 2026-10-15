"""پنل مدیریت سینتل - تنظیمات API و کاتالوگ."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
from config import ADMIN_IDS
from services.sintel import SintelClient, SintelError, _humanize_error, invalidate_catalog_cache
from services.sintel_catalog import sync_catalog_from_provider
from utils import esc, mask, parse_number, safe_edit

router = Router()
log = logging.getLogger(__name__)

# فیلتر ادمین
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


class SintelAdminStates(StatesGroup):
    """وضعیت‌های تنظیم."""
    api_key = State()
    profit_percent = State()


def _format_balance(balance: float) -> str:
    """فرمت‌دهی موجودی."""
    if balance is None:
        return "⚠️ خطا در دریافت"
    return f"{balance:,.0f} تومان"


async def _get_sintel_status() -> dict:
    """دریافت وضعیت کلی سینتل."""
    api_key = await db.get_setting("sintel_api")
    enabled = await db.get_setting("sintel_enabled")
    last_sync = await db.get_setting("sintel_last_sync")

    status = {
        "enabled": enabled == "1",
        "api_key_set": bool(api_key),
        "last_sync": last_sync or "هرگز",
        "balance": None,
        "service_count": 0,
    }

    if api_key:
        try:
            client = SintelClient(api_key)
            status["balance"] = await client.get_balance()

            # شمارش سرویس‌ها
            async with db._db.execute(
                "SELECT COUNT(*) FROM sintel_services WHERE is_active=1"
            ) as cur:
                row = await cur.fetchone()
                status["service_count"] = row[0] if row else 0

        except SintelError as exc:
            status["error"] = _humanize_error(exc)

    return status


# ---- منوی اصلی پنل سینتل ----
@router.callback_query(F.data == "panel_sintel")
async def cb_sintel_admin(call: CallbackQuery, state: FSMContext) -> None:
    """صفحه اصلی پنل سینتل."""
    await state.clear()
    await call.answer()

    status = await _get_sintel_status()

    if status.get("error"):
        error_text = f"\n⚠️ {status['error']}"
    else:
        error_text = ""

    text = (
        "🔌 <b>پنل مدیریت سینتل</b>\n\n"
        f"🔑 API: {'✅ تنظیم شده' if status['api_key_set'] else '❌ تنظیم نشده'}\n"
        f"🔄 وضعیت: {'✅ فعال' if status['enabled'] else '❌ غیرفعال'}\n"
        f"💰 موجودی: {_format_balance(status.get('balance'))}\n"
        f"📦 سرویس‌ها: {status['service_count']} عدد\n"
        f"🕐 آخرین همگام‌سازی: <code>{status['last_sync']}</code>\n"
        f"{error_text}\n\n"
        "👇 عملیات مورد نظر را انتخاب کن:"
    )

    await safe_edit(call, text, kb.sintel_admin_menu(status))


@router.callback_query(F.data == "sintel_set_api")
async def cb_sintel_set_api(call: CallbackQuery, state: FSMContext) -> None:
    """تنظیم کلید API."""
    await state.set_state(SintelAdminStates.api_key)

    current_key = await db.get_setting("sintel_api")
    shown = mask(current_key) if current_key else "—"

    text = (
        "🔑 <b>تنظیم کلید API سینتل</b>\n\n"
        f"🔑 کلید فعلی: <code>{shown}</code>\n\n"
        "📝 کلید API را از پنل سینتل کپی کرده و بفرست:\n"
        "<code>https://sintell.ir</code>"
    )

    await safe_edit(call, text, kb.cancel_kb("panel_sintel"))
    await call.answer()


@router.message(SintelAdminStates.api_key)
async def msg_sintel_api_key(message: Message, state: FSMContext) -> None:
    """ذخیره کلید API."""
    api_key = (message.text or "").strip()

    if not api_key:
        await message.answer("❌ کلید نمی‌تواند خالی باشد.")
        return

    # تست اتصال
    try:
        client = SintelClient(api_key)
        balance = await client.get_balance()
    except SintelError as exc:
        await message.answer(
            f"❌ <b>خطا در اتصال</b>\n\n{_humanize_error(exc)}\n\n"
            "کلید را بررسی کرده و دوباره بفرست:",
            reply_markup=kb.cancel_kb("panel_sintel")
        )
        return

    # ذخیره
    await db.set_setting("sintel_api", api_key)

    # حذف پیام حاوی کلید
    try:
        await message.delete()
    except Exception:
        pass

    await state.clear()
    await message.answer(
        f"✅ <b>کلید API با موفقیت ذخیره شد!</b>\n\n"
        f"💰 موجودی: <b>{balance:,.0f} تومان</b>",
        reply_markup=kb.sintel_admin_back()
    )


@router.callback_query(F.data == "sintel_toggle")
async def cb_sintel_toggle(call: CallbackQuery) -> None:
    """فعال/غیرفعال کردن سینتل."""
    current = await db.get_setting("sintel_enabled")
    new = "0" if current == "1" else "1"

    await db.set_setting("sintel_enabled", new)

    status = "✅ فعال شد" if new == "1" else "❌ غیرفعال شد"
    await call.answer(status, show_alert=True)

    await cb_sintel_admin(call, None)


@router.callback_query(F.data == "sintel_test_connection")
async def cb_sintel_test(call: CallbackQuery) -> None:
    """تست اتصال API."""
    await call.answer("⏳ در حال تست...")

    api_key = await db.get_setting("sintel_api")
    if not api_key:
        await call.answer("❌ کلید API تنظیم نشده.", show_alert=True)
        return

    try:
        client = SintelClient(api_key)
        balance = await client.get_balance()
        await call.answer(
            f"✅ <b>اتصال موفق!</b>\n\n💰 موجودی: {balance:,.0f} تومان",
            show_alert=True
        )
    except SintelError as exc:
        await call.answer(
            f"❌ <b>خطا در اتصال</b>\n\n{_humanize_error(exc)}",
            show_alert=True
        )


@router.callback_query(F.data == "sintel_sync_catalog")
async def cb_sintel_sync(call: CallbackQuery) -> None:
    """همگام‌سازی کاتالوگ."""
    await call.answer("⏳ در حال همگام‌سازی...\nاین عملیات چند ثانیه طول می‌کشد.")

    api_key = await db.get_setting("sintel_api")
    if not api_key:
        await call.answer("❌ کلید API تنظیم نشده.", show_alert=True)
        return

    # نمایش پیام در حال انتظار
    await safe_edit(call, "🔄 <b>در حال همگام‌سازی کاتالوگ...</b>\n\nلطفاً صبر کنید.", None)

    result = await sync_catalog_from_provider(api_key)

    if result.get("success"):
        # ذخیره زمان همگام‌سازی
        await db.set_setting(
            "sintel_last_sync",
            datetime.now().strftime("%Y-%m-%d %H:%M")
        )

        text = (
            "✅ <b>همگام‌سازی با موفقیت انجام شد!</b>\n\n"
            f"📊 کل سرویس‌ها: {result.get('total', 0)}\n"
            f"👥 تلگرام: {result.get('telegram', 0)}\n"
            f"📸 اینستاگرام: {result.get('instagram', 0)}\n"
            f"❓ سایر: {result.get('unknown', 0)}\n\n"
            "✅ سرویس‌ها در دیتابیس ذخیره شدند."
        )
    else:
        text = (
            f"❌ <b>خطا در همگام‌سازی</b>\n\n"
            f"{result.get('error', 'خطای نامشخص')}"
        )

    await safe_edit(call, text, kb.sintel_admin_back())
    await call.answer()


@router.callback_query(F.data == "sintel_set_profit")
async def cb_sintel_set_profit(call: CallbackQuery, state: FSMContext) -> None:
    """تنظیم درصد سود."""
    await state.set_state(SintelAdminStates.profit_percent)

    current = await db.get_float("sintel_profit_percent",
                                  await db.get_float("profit_percent", 30))

    text = (
        "📈 <b>تنظیم درصد سود سینتل</b>\n\n"
        f"📊 سود فعلی: <b>{current:g}%</b>\n\n"
        "📝 درصد سود را وارد کن (عدد بین 0 تا 100):\n"
        "مثال: <code>30</code> یا <code>25.5</code>\n\n"
        "💡 برای استفاده از سود پیش‌فرض، عدد <code>0</code> را بزن."
    )

    await safe_edit(call, text, kb.cancel_kb("panel_sintel"))
    await call.answer()


@router.message(SintelAdminStates.profit_percent)
async def msg_sintel_profit(message: Message, state: FSMContext) -> None:
    """ذخیره درصد سود."""
    number = parse_number(message.text or "")

    if number is None:
        await message.answer("❌ عدد نامعتبر. دوباره بفرست:",
                             reply_markup=kb.cancel_kb("panel_sintel"))
        return

    if number < 0 or number > 100:
        await message.answer("❌ درصد باید بین 0 تا 100 باشد.",
                            reply_markup=kb.cancel_kb("panel_sintel"))
        return

    # ذخیره
    if number == 0:
        # استفاده از سود پیش‌فرض - حذف تنظیم خاص
        await db.set_setting("sintel_profit_percent", "")
        profit_text = "سود پیش‌فرض (از تنظیمات اصلی)"
    else:
        await db.set_setting("sintel_profit_percent", f"{number:g}")
        profit_text = f"{number:g}%"

    await state.clear()
    await message.answer(
        f"✅ <b>سود سینتل تنظیم شد:</b> {profit_text}",
        reply_markup=kb.sintel_admin_back()
    )


@router.callback_query(F.data == "sintel_view_catalog")
async def cb_sintel_view_catalog(call: CallbackQuery) -> None:
    """مشاهده کاتالوگ."""
    # دریافت آمار
    async with db._db.execute("""
        SELECT platform, COUNT(*) as count
        FROM sintel_services
        WHERE is_active=1
        GROUP BY platform
    """) as cur:
        stats = {row[0]: row[1] for row in await cur.fetchall()}

    text = (
        "📦 <b>کاتالوگ سرویس‌های سینتل</b>\n\n"
        f"👥 تلگرام: {stats.get('telegram', 0)} سرویس\n"
        f"📸 اینستاگرام: {stats.get('instagram', 0)} سرویس\n"
        f"📊 کل: {sum(stats.values())} سرویس\n\n"
        "📝 برای مشاهده جزئیات، به کاتالوگ مراجعه کنید."
    )

    await safe_edit(call, text, kb.sintel_catalog_menu())
    await call.answer()


@router.callback_query(F.data.startswith("sintel_cat:"))
async def cb_sintel_catalog_platform(call: CallbackQuery) -> None:
    """نمایش سرویس‌های یک پلتفرم."""
    try:
        platform = call.data.split(":", 1)[1]
    except ValueError:
        await call.answer()
        return

    emoji = "👥" if platform == "telegram" else "📸"
    title = "تلگرام" if platform == "telegram" else "اینستاگرام"

    # دریافت سرویس‌ها
    async with db._db.execute("""
        SELECT service_id, name, rate, min_quantity, max_quantity, subcategory
        FROM sintel_services
        WHERE platform=? AND is_active=1
        ORDER BY subcategory, name
        LIMIT 50
    """, (platform,)) as cur:
        services = [dict(row) for row in await cur.fetchall()]

    if not services:
        await safe_edit(
            call,
            f"{emoji} <b>هیچ سرویس {title}ی یافت نشد.</b>\n\n"
            "ابتدا کاتالوگ را همگام‌سازی کنید.",
            kb.sintel_admin_back()
        )
        return

    # گروه‌بندی بر اساس زیرشاخه
    from services.sintel_catalog import SERVICE_CATEGORIES
    subcats = SERVICE_CATEGORIES.get(platform, {}).get("subcategories", {})

    text = f"{emoji} <b>سرویس‌های {title}</b>\n\n"

    current_subcat = None
    for service in services[:30]:  # محدود به 30 مورد
        subcat = service.get("subcategory", "other")
        if subcat != current_subcat:
            current_subcat = subcat
            cat_info = subcats.get(subcat, {})
            cat_title = cat_info.get("title", "سایر")
            cat_emoji = cat_info.get("emoji", "📊")
            text += f"\n{cat_emoji} {cat_title}:\n"

        text += f"  • {service['name'][:40]}\n"

    if len(services) > 30:
        text += f"\n... و {len(services) - 30} سرویس دیگر"

    await safe_edit(call, text, kb.sintel_admin_back())
    await call.answer()


@router.callback_query(F.data == "sintel_clear_cache")
async def cb_sintel_clear_cache(call: CallbackQuery) -> None:
    """پاک کردن کش."""
    invalidate_catalog_cache()
    await call.answer("✅ کش پاک شد.", show_alert=True)
    await cb_sintel_admin(call, None)


# ---- دسترسی ادمین ----
def sintel_admin_required(func):
    """دکوراتور بررسی دسترسی ادمین."""
    async def wrapper(call: CallbackQuery, state: FSMContext = None):
        if call.from_user.id not in ADMIN_IDS:
            await call.answer("⛔️ دسترسی ادمین لازم است.", show_alert=True)
            return
        return await func(call, state)
    return wrapper
