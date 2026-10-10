"""SimPars - کیف پول و شارژ با زیبال"""
from __future__ import annotations

import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import texts
from services import zibal
from services.payments import get_callback_url, get_merchant, process_payment
from utils import parse_number, safe_edit

router = Router()


class WalletStates(StatesGroup):
    amount = State()


async def _limits() -> tuple[int, int]:
    return await db.get_int("min_deposit", 10000), await db.get_int("max_deposit", 10000000)


async def _build_invoice(user_id: int, amount: int):
    """خروجی: (متن, کیبورد)"""
    low, high = await _limits()
    if amount < low or amount > high:
        return texts.BAD_AMOUNT.format(min=low, max=high), kb.wallet_kb()
    merchant = await get_merchant()
    if not merchant:
        return texts.GATEWAY_DISABLED, kb.back_main()
    try:
        track_id = await zibal.create_payment(
            merchant, amount * 10, await get_callback_url(),
            description=f"شارژ کیف پول سیم‌پارس - کاربر {user_id}",
            order_id=f"{user_id}-{int(time.time())}",
        )
    except zibal.ZibalError as exc:
        return f"⚠️ <b>خطا در ایجاد فاکتور</b>\n\n{exc}", kb.back_main()
    await db.create_payment(user_id, amount, track_id)
    return (texts.PAYMENT_CREATED.format(amount=amount, track=track_id),
            kb.payment_kb(zibal.payment_url(track_id), track_id))


@router.callback_query(F.data == "wallet")
async def cb_wallet(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await db.get_user(call.from_user.id)
    low, high = await _limits()
    await safe_edit(call, texts.WALLET.format(balance=user["balance"] if user else 0, min=low, max=high), kb.wallet_kb())
    await call.answer()


@router.callback_query(F.data.startswith("dep:"))
async def cb_deposit(call: CallbackQuery) -> None:
    try:
        amount = int(call.data.split(":")[1])
    except (ValueError, IndexError):
        await call.answer()
        return
    await call.answer("⏳ در حال ساخت فاکتور...")
    text, markup = await _build_invoice(call.from_user.id, amount)
    await safe_edit(call, text, markup)


@router.callback_query(F.data == "dep_custom")
async def cb_custom(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(WalletStates.amount)
    await safe_edit(call, texts.ENTER_AMOUNT, kb.cancel_kb("wallet"))
    await call.answer()


@router.message(WalletStates.amount)
async def msg_amount(message: Message, state: FSMContext) -> None:
    number = parse_number(message.text or "")
    if number is None or number <= 0:
        low, high = await _limits()
        await message.answer(texts.BAD_AMOUNT.format(min=low, max=high), reply_markup=kb.cancel_kb("wallet"))
        return
    await state.clear()
    wait = await message.answer("⏳ در حال ساخت فاکتور...")
    text, markup = await _build_invoice(message.from_user.id, int(number))
    await wait.edit_text(text, reply_markup=markup)


@router.callback_query(F.data.startswith("vfy:"))
async def cb_verify(call: CallbackQuery) -> None:
    track_id = call.data.split(":", 1)[1]
    payment = await db.get_payment(track_id)
    if not payment or payment["user_id"] != call.from_user.id:
        await call.answer("❌ تراکنش پیدا نشد.", show_alert=True)
        return
    ok, message = await process_payment(call.bot, track_id, notify_user=False)
    if ok:
        await call.answer("✅ پرداخت تایید شد!")
        await safe_edit(call, message, kb.markup([
            [kb.btn("🛒 خرید شماره مجازی", "buy")], [kb.btn("🏠 منوی اصلی", "home")],
        ]))
    else:
        await call.answer(message, show_alert=True)
