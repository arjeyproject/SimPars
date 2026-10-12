"""نمایش کاربران اخیر در پنل مدیریت."""
from __future__ import annotations

import time

from aiogram import F, Router
from aiogram.types import CallbackQuery

import database as db
import keyboards as kb
from config import ADMIN_IDS
from utils import esc, safe_edit

router = Router()
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


async def _recent_users(limit: int = 10):
    async with db._db.execute(
        "SELECT user_id, username, full_name, contact_phone, balance, is_banned, created_at "
        "FROM users ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ) as cursor:
        return await cursor.fetchall()


def _format_user(row, index: int) -> str:
    username = f"@{esc(row['username'])}" if row['username'] else "بدون یوزرنیم"
    name = esc(row['full_name'] or "بدون نام")
    joined = time.strftime("%Y/%m/%d %H:%M", time.localtime(row['created_at']))
    status = "🚫 مسدود" if row['is_banned'] else "✅ فعال"
    contact = "✅ ثبت شده" if row['contact_phone'] else "❌ ثبت نشده"
    return (
        f"{index}. <b>{name}</b> | {username}\n"
        f"   🆔 <code>{row['user_id']}</code> | {status}\n"
        f"   📅 {joined} | 📱 تماس: {contact} | 💰 {row['balance']:,} تومان"
    )


@router.callback_query(F.data == "adm_recent_users")
async def show_recent_users(call: CallbackQuery) -> None:
    rows = await _recent_users(10)
    if rows:
        body = "\n\n".join(_format_user(row, index) for index, row in enumerate(rows, 1))
        text = "👥 <b>کاربران اخیر ربات</b>\n\n" + body
    else:
        text = "👥 <b>کاربران اخیر ربات</b>\n\nهنوز کاربری ثبت نشده است."
    await safe_edit(call, text, kb.markup([
        [kb.btn("🔄 بروزرسانی", "adm_recent_users", style="primary")],
        [kb.btn("🔙 بازگشت به پنل", "admin", style="danger")],
    ]))
    await call.answer()
