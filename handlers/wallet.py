"""SimPars - کیف پول و شارژ با زرین‌پال."""
from __future__ import annotations
import time
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
import database as db
import keyboards as kb
import texts
from services import zarinpal
from services.payments import get_callback_url, get_merchant, is_sandbox, process_payment_result
from utils import esc, parse_number, safe_edit
router = Router()
class WalletStates(StatesGroup): amount = State()
async def _limits(): return await db.get_int("min_deposit", 10000), await db.get_int("max_deposit", 10000000)
async def _build_invoice(user_id: int, amount: int):
    low, high = await _limits()
    if amount < low or amount > high: return texts.BAD_AMOUNT.format(min=low, max=high), kb.wallet_kb()
    merchant = await get_merchant()
    if not merchant: return texts.GATEWAY_DISABLED, kb.back_main()
    user = await db.get_user(user_id)
    mobile = user["contact_phone"] if user and "contact_phone" in user.keys() else None
    try: authority = await zarinpal.create_payment(merchant, amount * 10, await get_callback_url(), description=f"شارژ کیف پول سیم‌پارس - کاربر {user_id}", order_id=f"wallet-{user_id}-{int(time.time())}", mobile=mobile)
    except zarinpal.ZarinpalError as exc: return f"⚠️ <b>خطا در ایجاد فاکتور</b>\n\n{esc(str(exc))}", kb.back_main()
    await db.create_payment(user_id, amount, authority)
    return texts.PAYMENT_CREATED.format(amount=amount), kb.payment_kb(zarinpal.payment_url(authority, sandbox=await is_sandbox()), authority)
@router.callback_query(F.data == "wallet")
async def cb_wallet(call: CallbackQuery, state: FSMContext):
    await state.clear(); user = await db.get_user(call.from_user.id); low, high = await _limits(); await safe_edit(call, texts.WALLET.format(balance=user["balance"] if user else 0, min=low, max=high), kb.wallet_kb()); await call.answer()
@router.callback_query(F.data.startswith("dep:"))
async def cb_deposit(call: CallbackQuery):
    try: amount = int(call.data.split(":")[1])
    except (ValueError, IndexError): await call.answer(); return
    await call.answer("⏳ در حال ساخت فاکتور..."); text, markup = await _build_invoice(call.from_user.id, amount); await safe_edit(call, text, markup)
@router.callback_query(F.data == "dep_custom")
async def cb_custom(call: CallbackQuery, state: FSMContext):
    await state.set_state(WalletStates.amount); await safe_edit(call, texts.ENTER_AMOUNT, kb.cancel_kb("wallet")); await call.answer()
@router.message(WalletStates.amount)
async def msg_amount(message: Message, state: FSMContext):
    number = parse_number(message.text or "")
    if number is None or number <= 0:
        low, high = await _limits(); await message.answer(texts.BAD_AMOUNT.format(min=low, max=high), reply_markup=kb.cancel_kb("wallet")); return
    await state.clear(); wait = await message.answer("⏳ در حال ساخت فاکتور..."); text, markup = await _build_invoice(message.from_user.id, int(number)); await wait.edit_text(text, reply_markup=markup)
@router.callback_query(F.data.startswith("vfy:"))
async def cb_verify(call: CallbackQuery):
    track_id = call.data.split(":", 1)[1]; payment = await db.get_payment(track_id)
    if not payment or payment["user_id"] != call.from_user.id: await call.answer("❌ تراکنش پیدا نشد.", show_alert=True); return
    result = await process_payment_result(call.bot, track_id, notify_user=False)
    if result.ok:
        try: await call.answer("✅ پرداخت تایید شد!")
        except Exception: pass
        await safe_edit(call, result.message, result.markup or kb.back_main()); return
    try: await call.answer(result.message[:190], show_alert=True)
    except Exception:
        try: await call.message.answer(result.message)
        except Exception: pass
