"""گزارش‌های مدیریتی خرید شماره‌ها."""
from __future__ import annotations

import time

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db
from config import ADMIN_IDS
from utils import esc, service_title

router = Router()
router.message.filter(lambda message: message.from_user.id in ADMIN_IDS)


@router.message(Command("sales"))
async def sales_report(message: Message) -> None:
    rows = await db.recent_orders(30)
    if not rows:
        await message.answer("📭 هنوز سفارشی ثبت نشده است.")
        return
    lines = ["📊 <b>گزارش ۳۰ سفارش اخیر</b>", "━━━━━━━━━━━━━━"]
    for order in rows:
        stamp = time.strftime("%Y/%m/%d %H:%M", time.localtime(order["created_at"]))
        lines.append(
            f"🆔 <code>#{order['id']}</code> | 👤 <code>{order['user_id']}</code>\n"
            f"📱 {service_title(order['product'])} | 🌍 {esc(order['country'])}\n"
            f"☎️ <code>{esc(order['phone'])}</code> | 💰 <b>{order['price']:,} تومان</b>\n"
            f"📌 {esc(order['status'])} | 🕒 {stamp}\n━━━━━━━━━━━━━━"
        )
    await message.answer("\n".join(lines))
