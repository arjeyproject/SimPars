"""Admin controls for the live USD pricing provider."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
from services.market import refresh_rate, snapshot
from utils import esc, safe_edit

router = Router()
router.callback_query.filter(F.from_user.id.in_(set()))


class MarketStates(StatesGroup):
    api_key = State()
    url = State()


def _is_admin(user_id: int) -> bool:
    from config import ADMIN_IDS
    return user_id in ADMIN_IDS


async def _render(call: CallbackQuery) -> None:
    data = await snapshot()
    text = (
        "💵 <b>نگهبان نرخ دلار</b>\n\n"
        f"📈 نرخ فعلی: <b>{esc(data['rate'])} تومان</b>\n"
        f"📡 منبع: <code>{esc(data['source'])}</code>\n"
        f"🕒 سن آخرین بروزرسانی: <b>{esc(data['age'])} ثانیه</b>\n"
        f"🛒 فروش: <b>{'فعال' if data['paused'] != '1' else 'متوقف امن'}</b>\n\n"
        "کلید و آدرس فقط در دیتابیس تنظیمات ذخیره می‌شوند و داخل سورس قرار نمی‌گیرند."
    )
    await safe_edit(call, text, kb.market_admin_kb(bool(await db.get_setting('usd_rate_api_key')), bool(await db.get_setting('usd_rate_url'))))


@router.callback_query(F.data == "market_admin")
async def market_panel(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        return
    await call.answer()
    await _render(call)


@router.callback_query(F.data == "market_set_key")
async def set_key(call: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(call.from_user.id):
        return
    await state.set_state(MarketStates.api_key)
    await safe_edit(call, "🔐 <b>کلید API نرخ دلار</b>\n\nکلید را بفرست؛ بعد از دریافت پیام حذف می‌شود.", kb.cancel_kb("market_admin"))
    await call.answer()


@router.message(MarketStates.api_key)
async def save_key(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    value = (message.text or "").strip().split()[0] if (message.text or "").strip() else ""
    if not value:
        await message.answer("❌ کلید خالی است.")
        return
    try:
        await message.delete()
    except Exception:
        pass
    await db.set_setting("usd_rate_api_key", value)
    await state.clear()
    ok, detail = await refresh_rate()
    await message.answer(("✅ کلید ذخیره و اتصال تست شد." if ok else f"⚠️ کلید ذخیره شد، اما تست ناموفق بود: <code>{esc(detail)}</code>") , reply_markup=kb.admin_back("market_admin"))


@router.callback_query(F.data == "market_set_url")
async def set_url(call: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(call.from_user.id):
        return
    await state.set_state(MarketStates.url)
    await safe_edit(call, "🌐 <b>آدرس API نرخ دلار</b>\n\nآدرس HTTPS سرویس خودت را بفرست.", kb.cancel_kb("market_admin"))
    await call.answer()


@router.message(MarketStates.url)
async def save_url(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    value = (message.text or "").strip()
    if not value.startswith("https://"):
        await message.answer("❌ فقط آدرس HTTPS قابل قبول است.")
        return
    await db.set_setting("usd_rate_url", value)
    await state.clear()
    ok, detail = await refresh_rate()
    await message.answer(("✅ آدرس ذخیره و اتصال تست شد." if ok else f"⚠️ آدرس ذخیره شد، اما تست ناموفق بود: <code>{esc(detail)}</code>") , reply_markup=kb.admin_back("market_admin"))


@router.callback_query(F.data == "market_refresh")
async def refresh(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        return
    ok, detail = await refresh_rate()
    await call.answer("✅ نرخ بروزرسانی شد" if ok else "⚠️ تست ناموفق بود", show_alert=not ok)
    await _render(call)
