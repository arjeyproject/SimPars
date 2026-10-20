"""Checkout router: coupon application and safe direct/wallet purchase."""
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
from services.fivesim import FiveSimClient, FiveSimError, PurchaseUnknownError, humanize
from services.market import sales_allowed
from services.purchase_checkout import create_invoice, resolve, reserve_order, complete_reserved_order, refund_reserved_order
from utils import esc, phone_ltr, safe_edit, service_title
router=Router(); log=logging.getLogger(__name__)
class CouponStates(StatesGroup): code=State(); create=State(); delete=State()
def _is_admin(uid:int)->bool:return uid in ADMIN_IDS
def _checkout_kb(can_wallet:bool,can_pay:bool=True):
    rows=[]
    if can_wallet:rows.append([kb.btn("💰 خرید از کیف پول","purchase_wallet",style="success")])
    if can_pay:rows.append([kb.btn("💳 پرداخت مستقیم همین مبلغ","purchase_pay",style="success")])
    rows.append([kb.btn("🎁 اعمال کد تخفیف","purchase_coupon",style="primary")]); rows.append([kb.btn("🏠 منوی اصلی","home",style="primary")]); return kb.markup(rows)
async def _show(call:CallbackQuery,payload:dict,notice:str=""):
    price,operator,code=await resolve(payload); payload["operator"]=operator
    user=await db.get_user(call.from_user.id); balance=int(user["balance"] if user else 0); coupon_text=f"\n🎁 تخفیف: <b>{esc(code)}</b>" if code else ""
    text=f"🧾 <b>پیش‌فاکتور خرید شماره</b>\n\n📲 سرویس: <b>{esc(service_title(payload['product']))}</b>\n🌍 کشور: <b>{esc(payload['country'])}</b>\n💰 مبلغ نهایی: <b>{price:,} تومان</b>{coupon_text}\n👛 موجودی کیف پول: <b>{balance:,} تومان</b>\n\n{notice or 'روش پرداخت را انتخاب کن.'}"
    await safe_edit(call,text,_checkout_kb(balance>=price,True))
@router.callback_query(F.data.startswith("ok:"))
async def purchase_preview(call:CallbackQuery,state:FSMContext):
    try:_,product,country,operator=call.data.split(":",3)
    except ValueError:await call.answer();return
    if not await sales_allowed():await call.answer(texts.SALES_DISABLED,show_alert=True);return
    payload={"product":product,"country":country,"operator":operator}; await state.clear(); await state.update_data(purchase=payload)
    try:
        price,selected,_=await resolve(payload); payload["operator"]=selected; await state.clear(); await state.update_data(purchase=payload)
        await _show(call,payload,"موجودی و شماره هنگام تأیید دوباره بررسی می‌شود.")
    except FiveSimError as exc:await call.answer(humanize(exc),show_alert=True);return
    await call.answer()
@router.callback_query(F.data=="purchase_coupon")
async def ask_coupon(call:CallbackQuery,state:FSMContext):
    if not await state.get_value("purchase"):await call.answer("پیش‌فاکتور منقضی شده؛ دوباره شماره را انتخاب کن.",show_alert=True);return
    await state.set_state(CouponStates.code); await call.message.answer("🎁 کد تخفیف را بفرست:"); await call.answer()
@router.message(CouponStates.code)
async def apply_coupon(message:Message,state:FSMContext):
    payload=await state.get_value("purchase"); valid,detail,_=await coupons.validate(message.text or "")
    if not valid:await message.answer(f"❌ {esc(detail)}\nدوباره بفرست:");return
    payload["coupon"]=(message.text or "").strip().upper(); await state.clear(); await state.update_data(purchase=payload); price,operator,_=await resolve(payload); payload["operator"]=operator; await state.update_data(purchase=payload); user=await db.get_user(message.from_user.id); balance=int(user["balance"] if user else 0)
    await message.answer(f"✅ کد اعمال شد.\n\nمبلغ نهایی: <b>{price:,} تومان</b>\nموجودی: <b>{balance:,} تومان</b>",reply_markup=_checkout_kb(balance>=price,True))
@router.callback_query(F.data=="purchase_pay")
async def pay_direct(call:CallbackQuery,state:FSMContext):
    payload=await state.get_value("purchase")
    if not payload:await call.answer("پیش‌فاکتور منقضی شده؛ دوباره شماره را انتخاب کن.",show_alert=True);return
    try:authority,price=await create_invoice(call.from_user.id,payload)
    except Exception:await call.answer("❌ ساخت فاکتور انجام نشد؛ دوباره تلاش کن.",show_alert=True);return
    sandbox=(await db.get_setting("zibal_sandbox"))=="1"; await call.message.answer(f"🧾 <b>فاکتور پرداخت شماره</b>\n\n💰 مبلغ دقیق: <b>{price:,} تومان</b>\n\n✅ بعد از پرداخت موفق، شماره به‌صورت خودکار ارسال می‌شود.",reply_markup=kb.payment_kb(zarinpal.payment_url(authority,sandbox=sandbox),authority)); await call.answer()
@router.callback_query(F.data=="purchase_wallet")
async def pay_wallet(call:CallbackQuery,state:FSMContext):
    payload=await state.get_value("purchase")
    if not payload:await call.answer("پیش‌فاکتور منقضی شده است؛ دوباره شماره را انتخاب کن.",show_alert=True);return
    try:price,operator,_=await resolve(payload)
    except FiveSimError as exc:await call.answer(humanize(exc),show_alert=True);return
    payload={**payload,"operator":operator}; order_id,created=await reserve_order(call.from_user.id,payload,price,wallet=True)
    if not created:
        if order_id:await call.answer("⏳ این خرید قبلاً شروع شده؛ خرید دوباره انجام نده.",show_alert=True)
        else:await call.answer("موجودی کافی نیست.",show_alert=True)
        return
    client=FiveSimClient(await db.get_setting("fivesim_api"))
    try:
        data=await client.buy(payload["country"],operator,payload["product"])
    except PurchaseUnknownError:
        log.error("ambiguous wallet purchase user=%s local_order=%s",call.from_user.id,order_id); await call.answer("⚠️ پاسخ سرویس نامشخص است؛ خرید دوباره انجام نده و با پشتیبانی تماس بگیر.",show_alert=True); return
    except FiveSimError as exc:
        # موجودی 5Sim لحظه‌ای است. اگر اپراتور انتخاب‌شده همین الان خالی شد،
        # یک‌بار قیمت‌ها را از نو می‌گیریم و با بهترین اپراتور موجود امتحان می‌کنیم.
        if "no free phones" in str(exc).lower():
            try:
                fresh={**payload,"operator":""}; fresh_price,fresh_operator,_=await resolve(fresh)
                if fresh_operator and fresh_operator.lower()!=operator.lower() and fresh_price<=price:
                    data=await client.buy(fresh["country"],fresh_operator,fresh["product"]); operator=fresh_operator; payload["operator"]=operator
                else:
                    await refund_reserved_order(order_id); await call.answer(humanize(exc),show_alert=True); return
            except PurchaseUnknownError:
                log.error("ambiguous retry wallet purchase user=%s local_order=%s",call.from_user.id,order_id); await call.answer("⚠️ پاسخ سرویس نامشخص است؛ خرید دوباره انجام نده و با پشتیبانی تماس بگیر.",show_alert=True); return
            except FiveSimError:
                await refund_reserved_order(order_id); await call.answer(humanize(exc),show_alert=True); return
        else:
            await refund_reserved_order(order_id); await call.answer(humanize(exc),show_alert=True); return
    if not await complete_reserved_order(order_id,data,operator):
        await call.answer("⚠️ شماره ایجاد شد اما ثبت سفارش نیازمند بررسی است؛ خرید دوباره انجام نده.",show_alert=True); return
    if payload.get("coupon"):
        try:await coupons.consume(payload["coupon"])
        except Exception:log.warning("coupon consume failed")
    await state.clear(); phone=str(data.get("phone") or ""); await call.answer("✅ شماره رزرو شد"); await safe_edit(call,texts.ORDER_CREATED.format(order_id=order_id,service=service_title(payload["product"]),country=esc(payload["country"]),phone=phone_ltr(phone),price=price,minutes=ORDER_LIFETIME//60),kb.order_kb(order_id))
@router.callback_query(F.data=="coupon_admin")
async def coupon_admin(call:CallbackQuery):
    if not _is_admin(call.from_user.id):return
    items=await coupons.list_coupons(); body="\n".join(f"<code>{esc(code)}</code>: {item['percent']}٪ | مصرف {item.get('uses',0)}/{item.get('max_uses') or '∞'}" for code,item in items.items()) or "هنوز کدی ساخته نشده."
    await safe_edit(call,f"🎁 <b>کدهای تخفیف</b>\n\n{body}",kb.markup([[kb.btn("➕ ایجاد کد","coupon_add",style="success")],[kb.btn("🗑 حذف کد","coupon_delete",style="danger")],[kb.btn("🔙 بازگشت به پنل","admin",style="primary")]])); await call.answer()
@router.callback_query(F.data=="coupon_add")
async def coupon_add(call:CallbackQuery,state:FSMContext):
    if not _is_admin(call.from_user.id):return
    await state.set_state(CouponStates.create); await call.message.answer("فرمت: CODE PERCENT MAX_USES\nمثال: <code>WELCOME20 20 100</code>"); await call.answer()
@router.message(CouponStates.create)
async def coupon_create(message:Message,state:FSMContext):
    if not _is_admin(message.from_user.id):return
    parts=(message.text or "").split()
    if len(parts)!=3:await message.answer("فرمت نادرست است: CODE PERCENT MAX_USES");return
    try:await coupons.create_coupon(parts[0],int(parts[1]),int(parts[2]))
    except ValueError:await message.answer("کد یا درصد نامعتبر است.");return
    await state.clear(); await message.answer("✅ کد تخفیف ساخته شد.",reply_markup=kb.admin_back("coupon_admin"))
@router.callback_query(F.data=="coupon_delete")
async def coupon_delete(call:CallbackQuery,state:FSMContext):
    if not _is_admin(call.from_user.id):return
    await state.set_state(CouponStates.delete); await call.message.answer("کدی که باید حذف شود را بفرست:"); await call.answer()
@router.message(CouponStates.delete)
async def coupon_delete_message(message:Message,state:FSMContext):
    if not _is_admin(message.from_user.id):return
    removed=await coupons.delete_coupon(message.text or ""); await state.clear(); await message.answer("✅ حذف شد." if removed else "❌ چنین کدی پیدا نشد.",reply_markup=kb.admin_back("coupon_admin"))
