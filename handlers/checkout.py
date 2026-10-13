"""Checkout router: coupon application and direct gateway invoice."""
from __future__ import annotations
import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
import database as db
import keyboards as kb
import texts
from config import ADMIN_IDS, ORDER_LIFETIME
from services import coupons, fivesim, zarinpal
from services.fivesim import FiveSimClient, FiveSimError
from services.market import sales_allowed
from services.purchase_checkout import create_invoice, resolve
from utils import esc, safe_edit, service_title
router = Router(); log = logging.getLogger(__name__)
class CouponStates(StatesGroup):
    code = State(); create = State(); delete = State()
def _is_admin(uid: int) -> bool: return uid in ADMIN_IDS
def _checkout_kb(can_wallet: bool, can_pay: bool = True):
    rows = []
    if can_wallet: rows.append([kb.btn("💰 خرید از کیف پول", "purchase_wallet", style="success")])
    if can_pay: rows.append([kb.btn("💳 پرداخت مستقیم همین مبلغ", "purchase_pay", style="success")])
    rows.append([kb.btn("🎁 اعمال کد تخفیف", "purchase_coupon", style="primary")]); rows.append([kb.btn("🏠 منوی اصلی", "home", style="danger")]); return kb.markup(rows)
async def _show(call: CallbackQuery, payload: dict, notice: str = ""):
    price, _, code = await resolve(payload); user = await db.get_user(call.from_user.id); balance = int(user["balance"] if user else 0); coupon_text = f"\n🎁 تخفیف: <b>{code}</b>" if code else ""
    text = f"🧾 <b>پیش‌فاکتور خرید شماره</b>\n\n📲 سرویس: <b>{service_title(payload['product'])}</b>\n🌍 کشور: <b>{esc(payload['country'])}</b>\n💰 مبلغ نهایی: <b>{price:,} تومان</b>{coupon_text}\n👛 موجودی کیف پول: <b>{balance:,} تومان</b>\n\n{notice or 'روش پرداخت را انتخاب کن.'}"
    await safe_edit(call, text, _checkout_kb(balance >= price, True))
@router.callback_query(F.data.startswith("ok:"))
async def purchase_preview(call: CallbackQuery, state: FSMContext):
    try: _, product, country, operator = call.data.split(":", 3)
    except ValueError: await call.answer(); return
    if not await sales_allowed(): await call.answer(texts.SALES_DISABLED, show_alert=True); return
    payload = {"product": product, "country": country, "operator": operator}; await state.clear(); await state.update_data(purchase=payload)
    try: await _show(call, payload, "اگر موجودی کافی نباشد، فاکتور دقیق همین مبلغ ساخته می‌شود.")
    except FiveSimError as exc: await call.answer(str(exc), show_alert=True); return
    await call.answer()
@router.callback_query(F.data == "purchase_coupon")
async def ask_coupon(call: CallbackQuery, state: FSMContext):
    if not await state.get_value("purchase"): await call.answer("پیش‌فاکتور منقضی شده؛ دوباره شماره را انتخاب کن.", show_alert=True); return
    await state.set_state(CouponStates.code); await call.message.answer("🎁 کد تخفیف را بفرست:"); await call.answer()
@router.message(CouponStates.code)
async def apply_coupon(message: Message, state: FSMContext):
    payload = await state.get_value("purchase"); valid, detail, _ = await coupons.validate(message.text or "")
    if not valid: await message.answer(f"❌ {detail}\nدوباره بفرست: "); return
    payload["coupon"] = (message.text or "").strip().upper(); await state.clear(); await state.update_data(purchase=payload); price, _, _ = await resolve(payload); user = await db.get_user(message.from_user.id); balance = int(user["balance"] if user else 0)
    await message.answer(f"✅ {detail}\n\nمبلغ نهایی: <b>{price:,} تومان</b>\nموجودی: <b>{balance:,} تومان</b>", reply_markup=_checkout_kb(balance >= price, True))
@router.callback_query(F.data == "purchase_pay")
async def pay_direct(call: CallbackQuery, state: FSMContext):
    payload = await state.get_value("purchase")
    if not payload: await call.answer("پیش‌فاکتور منقضی شده؛ دوباره شماره را انتخاب کن.", show_alert=True); return
    try: authority, price = await create_invoice(call.from_user.id, payload)
    except Exception as exc: await call.answer(str(exc), show_alert=True); return
    sandbox = (await db.get_setting("zibal_sandbox")) == "1"
    await call.message.answer(f"🧾 <b>فاکتور پرداخت شماره</b>\n\n💰 مبلغ دقیق: <b>{price:,} تومان</b>\n\n✅ بعد از پرداخت موفق، شماره به‌صورت خودکار ارسال می‌شود.", reply_markup=kb.payment_kb(zarinpal.payment_url(authority, sandbox=sandbox), authority)); await call.answer()
@router.callback_query(F.data == "purchase_wallet")
async def pay_wallet(call: CallbackQuery, state: FSMContext):
    payload = await state.get_value("purchase")
    if not payload: await call.answer("پیش‌فاکتور منقضی شده است.", show_alert=True); return
    try: price, operator, coupon_code = await resolve(payload)
    except FiveSimError as exc: await call.answer(str(exc), show_alert=True); return
    if not await db.deduct_balance(call.from_user.id, price): await call.answer("موجودی کافی نیست؛ پرداخت مستقیم را بزن.", show_alert=True); return
    try: data = await FiveSimClient(await db.get_setting("fivesim_api")).buy(payload["country"], operator, payload["product"])
    except FiveSimError as exc: await db.add_balance(call.from_user.id, price); await call.answer("خرید انجام نشد و مبلغ برگشت خورد.", show_alert=True); log.warning("wallet purchase failed: %s", exc); return
    order_id = await db.create_order(call.from_user.id, int(data["id"]), str(data.get("phone") or ""), payload["product"], payload["country"], str(data.get("operator") or operator), price, ORDER_LIFETIME)
    if coupon_code: await coupons.consume(coupon_code)
    await state.clear(); await call.answer("✅ شماره رزرو شد"); await safe_edit(call, texts.ORDER_CREATED.format(order_id=order_id, service=service_title(payload["product"]), country=esc(payload["country"]), phone=esc(str(data.get("phone") or "")), price=price, minutes=ORDER_LIFETIME // 60), kb.order_kb(order_id))
@router.callback_query(F.data == "coupon_admin")
async def coupon_admin(call: CallbackQuery):
    if not _is_admin(call.from_user.id): return
    items = await coupons.list_coupons(); body = "\n".join(f"<code>{esc(code)}</code>: {item['percent']}٪ | مصرف {item.get('uses', 0)}/{item.get('max_uses') or '∞'}" for code, item in items.items()) or "هنوز کدی ساخته نشده."
    await safe_edit(call, f"🎁 <b>کدهای تخفیف</b>\n\n{body}", kb.markup([[kb.btn("➕ ایجاد کد", "coupon_add", style="success")], [kb.btn("🗑 حذف کد", "coupon_delete", style="danger")], [kb.btn("🔙 بازگشت به پنل", "admin", style="danger")]])); await call.answer()
@router.callback_query(F.data == "coupon_add")
async def coupon_add(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id): return
    await state.set_state(CouponStates.create); await call.message.answer("فرمت: CODE PERCENT MAX_USES\nمثال: <code>WELCOME20 20 100</code>\nبرای مصرف نامحدود MAX_USES را 0 بگذار."); await call.answer()
@router.message(CouponStates.create)
async def coupon_create(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    parts = (message.text or "").split()
    if len(parts) != 3: await message.answer("فرمت نادرست است: CODE PERCENT MAX_USES"); return
    try: await coupons.create_coupon(parts[0], int(parts[1]), int(parts[2]))
    except ValueError: await message.answer("کد یا درصد نامعتبر است."); return
    await state.clear(); await message.answer("✅ کد تخفیف ساخته شد.", reply_markup=kb.admin_back("coupon_admin"))
@router.callback_query(F.data == "coupon_delete")
async def coupon_delete(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id): return
    await state.set_state(CouponStates.delete); await call.message.answer("کدی که باید حذف شود را بفرست:"); await call.answer()
@router.message(CouponStates.delete)
async def coupon_delete_message(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    removed = await coupons.delete_coupon(message.text or ""); await state.clear(); await message.answer("✅ حذف شد." if removed else "❌ چنین کدی پیدا نشد.", reply_markup=kb.admin_back("coupon_admin"))
