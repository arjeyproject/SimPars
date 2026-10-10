"""SimPars - پاسخ به پیام‌ها و دکمه‌های ناشناخته"""
from aiogram import Router
from aiogram.types import CallbackQuery, Message

import keyboards as kb
import texts
from config import ADMIN_IDS

router = Router()


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer(texts.UNKNOWN, reply_markup=kb.main_menu(message.from_user.id in ADMIN_IDS))


@router.callback_query()
async def unknown_callback(call: CallbackQuery) -> None:
    await call.answer("⚠️ این دکمه منقضی شده؛ /start رو بزن.", show_alert=True)
