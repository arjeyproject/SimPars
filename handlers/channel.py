"""مدیریت کانال قفل اجباری از پنل ادمین."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
from config import CHANNEL_USERNAME
from utils import esc, safe_edit

router = Router()


class ChannelStates(StatesGroup):
    waiting_channel = State()


def _channel_url(value: str) -> str:
    return "https://t.me/" + value.lstrip("@") if value.startswith("@") else ""


def _channel_kb() -> object:
    return kb.markup([
        [kb.btn("✏️ ثبت / تغییر کانال", "channel_set", style="primary")],
        [kb.btn("🗑 حذف کانال سفارشی", "channel_clear", style="danger")],
        [kb.btn("🔙 بازگشت به پنل", "admin", style="danger")],
    ])


@router.callback_query(F.data == "channel_admin")
async def show_channel_settings(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    value = (await db.get_setting("force_join_channel")).strip() or CHANNEL_USERNAME
    text = (
        "📢 <b>کانال قفل اجباری</b>\n\n"
        f"کانال فعال: <code>{esc(value)}</code>\n\n"
        "برای بررسی عضویت، ربات باید داخل کانال ادمین باشد.\n"
        "برای ثبت، یوزرنیم عمومی مثل <code>@SimPars</code> یا شناسه عددی کانال مثل <code>-1001234567890</code> را وارد کن."
    )
    await safe_edit(call, text, _channel_kb())
    await call.answer()


@router.callback_query(F.data == "channel_set")
async def start_channel_set(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChannelStates.waiting_channel)
    await safe_edit(call, "📢 شناسه کانال را بفرست:\n\nمثال: <code>@SimPars</code> یا <code>-1001234567890</code>", kb.cancel_kb("channel_admin"))
    await call.answer()


@router.message(ChannelStates.waiting_channel)
async def save_channel(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if value == "-":
        await db.set_setting("force_join_channel", "")
    elif value.startswith("@") and len(value) > 2 and all(ch.isalnum() or ch == "_" for ch in value[1:]):
        await db.set_setting("force_join_channel", value)
    elif value.startswith("-100") and value[4:].isdigit():
        await db.set_setting("force_join_channel", value)
    else:
        await message.answer("❌ شناسه نامعتبر است. فقط @username یا شناسه عددی -100... بفرست.", reply_markup=kb.cancel_kb("channel_admin"))
        return
    await state.clear()
    active = (await db.get_setting("force_join_channel")).strip() or CHANNEL_USERNAME
    await message.answer(f"✅ کانال قفل اجباری روی <code>{esc(active)}</code> تنظیم شد.", reply_markup=kb.admin_back())


@router.callback_query(F.data == "channel_clear")
async def clear_channel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await db.set_setting("force_join_channel", "")
    await call.answer("✅ کانال سفارشی حذف شد")
    await show_channel_settings(call, state)
