"""SimPars - میدلور دسترسی (ثبت کاربر، مسدودی، تعمیرات، جوین اجباری، رفرال)"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject

import database as db
import keyboards as kb
import texts
from config import ADMIN_IDS, CHANNEL_USERNAME

log = logging.getLogger(__name__)


async def is_member(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
    except Exception as exc:  # noqa: BLE001
        # ربات در کانال ادمین نیست یا کانال اشتباه است؛ کاربر را مسدود نمی‌کنیم
        log.warning("force-join check failed: %s", exc)
        return True
    status = str(getattr(member.status, "value", member.status))
    if status in ("left", "kicked"):
        return False
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    return True


async def _handle_referral(bot: Bot, message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].startswith("ref_"):
        return
    ref = parts[1][4:]
    if not ref.isdigit():
        return
    ref_id = int(ref)
    if ref_id == message.from_user.id or not await db.get_user(ref_id):
        return
    if await db.set_referrer(message.from_user.id, ref_id):
        try:
            await bot.send_message(
                ref_id,
                "🎉 <b>یه دوست جدید با لینک دعوتت عضو شد!</b>\n"
                "💰 از این به بعد از هر شارژش هدیه می‌گیری 🎁",
            )
        except Exception:  # noqa: BLE001
            pass


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)

        chat = event.chat if isinstance(event, Message) else (
            event.message.chat if isinstance(event, CallbackQuery) and event.message else None
        )
        if chat is not None and chat.type != "private":
            return None

        bot: Bot = data["bot"]
        created = await db.ensure_user(user.id, user.username, user.full_name)
        if created and isinstance(event, Message):
            await _handle_referral(bot, event)

        if user.id in ADMIN_IDS:
            return await handler(event, data)

        row = await db.get_user(user.id)
        if row and row["is_banned"]:
            return await self._deny(event, texts.BANNED, alert="🚫 دسترسی شما مسدود است.")
        if await db.get_setting("maintenance") == "1":
            return await self._deny(event, texts.MAINTENANCE, alert="🛠 ربات در حال بروزرسانی است.")
        if await db.get_setting("force_join") == "1" and not await is_member(bot, user.id):
            if isinstance(event, CallbackQuery) and event.data == "joined":
                await event.answer("❌ هنوز عضو کانال نشدی!", show_alert=True)
                return None
            return await self._deny(event, texts.FORCE_JOIN, markup=kb.join_kb())
        return await handler(event, data)

    @staticmethod
    async def _deny(event: TelegramObject, text: str, markup=None, alert: str | None = None):
        if isinstance(event, Message):
            await event.answer(text, reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            if alert:
                await event.answer(alert, show_alert=True)
            else:
                await event.answer()
                if event.message:
                    await event.message.answer(text, reply_markup=markup)
        return None
