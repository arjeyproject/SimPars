"""بخش‌های عمومی کاربر."""
from __future__ import annotations

import time

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import texts
from config import ADMIN_IDS, BOT_USERNAME
from utils import country_title, esc, safe_edit, service_title

router = Router()


def welcome(user) -> str:
    return texts.WELCOME.format(name=esc(user.first_name or "دوست"))


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(welcome(message.from_user), reply_markup=kb.main_menu(message.from_user.id in ADMIN_IDS))


@router.callback_query(F.data == "home")
async def cb_home(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(call, welcome(call.from_user), kb.main_menu(call.from_user.id in ADMIN_IDS))
    await call.answer()


@router.callback_query(F.data == "joined")
async def cb_joined(call: CallbackQuery) -> None:
    await call.answer("✅ عضویتت تایید شد، خوش اومدی!")
    await safe_edit(call, welcome(call.from_user), kb.main_menu(call.from_user.id in ADMIN_IDS))


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data == "account")
async def cb_account(call: CallbackQuery) -> None:
    user = await db.get_user(call.from_user.id)
    orders, spent = await db.user_stats(call.from_user.id)
    refs = await db.count_referrals(call.from_user.id)
    username = f"@{esc(call.from_user.username)}" if call.from_user.username else "—"
    created = user["created_at"] if user else time.time()
    text = texts.ACCOUNT.format(
        uid=call.from_user.id, name=esc(call.from_user.full_name), username=username,
        balance=user["balance"] if user else 0, orders=orders, spent=spent, refs=refs,
        joined=time.strftime("%Y/%m/%d", time.localtime(created)),
    )
    await safe_edit(call, text, kb.markup([
        [kb.btn("💰 شارژ کیف پول", "wallet"), kb.btn("📦 سفارش‌ها", "orders")],
        [kb.btn("🏠 منوی اصلی", "home")],
    ]))
    await call.answer()


@router.callback_query(F.data == "orders")
async def cb_orders(call: CallbackQuery) -> None:
    orders = await db.user_orders(call.from_user.id, 10)
    if not orders:
        await safe_edit(call, texts.NO_ORDERS, kb.markup([
            [kb.btn("🛒 خرید شماره مجازی", "buy")], [kb.btn("🏠 منوی اصلی", "home")],
        ]))
        await call.answer()
        return

    lines = ["📦 <b>۱۰ سفارش اخیر شما</b>", "━━━━━━━━━━━━━━"]
    rows = []
    for order in orders:
        created = time.strftime("%m/%d %H:%M", time.localtime(order["created_at"]))
        status = texts.ORDER_STATUS.get(order["status"], "⚠️ وضعیت نامشخص")
        lines.extend([
            f"🆔 <code>#{order['id']}</code> | {service_title(order['product'])} | {country_title(order['country'])}",
            f"📅 {created} | 💰 <b>{order['price']:,} تومان</b>",
            f"📞 <code>{esc(order['phone'])}</code> | {status}",
            f"🔑 کد: <code>{esc(order['code'] or '—')}</code>",
            "━━━━━━━━━━━━━━",
        ])
        if order["status"] in ("PENDING", "RECEIVED"):
            rows.append([kb.btn(f"🔄 پیگیری سفارش #{order['id']}", f"chk:{order['id']}")])

    rows.extend([
        [kb.btn("🛒 خرید شماره جدید", "buy")],
        [kb.btn("🏠 منوی اصلی", "home")],
    ])
    await safe_edit(call, "\n".join(lines), kb.markup(rows))
    await call.answer()


@router.callback_query(F.data == "referral")
async def cb_referral(call: CallbackQuery) -> None:
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{call.from_user.id}"
    percent = await db.get_float("referral_percent", 0)
    count = await db.count_referrals(call.from_user.id)
    text = texts.REFERRAL.format(percent=f"{percent:g}", count=count, link=link)
    await safe_edit(call, text, kb.referral_kb(link))
    await call.answer()


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery) -> None:
    custom = (await db.get_setting("support_text")).strip()
    await safe_edit(call, custom or texts.DEFAULT_SUPPORT, kb.support_kb())
    await call.answer()


@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery) -> None:
    await safe_edit(call, texts.HELP, kb.markup([
        [kb.btn("🛒 خرید شماره مجازی", "buy")], [kb.btn("🏠 منوی اصلی", "home")],
    ]))
    await call.answer()
