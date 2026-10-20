"""Virtual-number storefront; checkout owns the single payment confirmation path."""
from __future__ import annotations
import asyncio,logging,math
from collections import defaultdict
from aiogram import F,Router
from aiogram.types import CallbackQuery
import database as db
import keyboards as kb
import texts
from config import ORDER_LIFETIME
from services import availability,fivesim
from services.fivesim import FiveSimClient,FiveSimError,PurchaseUnknownError,humanize
from services.market import sales_allowed
from services.orders import code_message,refund,sync_order
from utils import calc_price,country_title,esc,phone_ltr,safe_edit,service_title
router=Router();log=logging.getLogger(__name__);PAGE_SIZE=10;_locks=defaultdict(asyncio.Lock)
SOLD_OUT="😕 موجودی این کشور همین الان تمام شد؛ کشور دیگری را انتخاب کن."
async def _pricing():return await db.get_float("rate",1000),max(0.0,await db.get_float("profit_percent",30))
async def _loading(call,frames,pause=.12):
    for frame in frames:
        try:await call.message.edit_text(frame);await asyncio.sleep(pause)
        except Exception:return
async def _preferred_operators():
    raw=await db.get_setting("fivesim_preferred_operators");return tuple(x.strip() for x in raw.replace("،",",").split(",") if x.strip())
async def _show_countries(call,product,page=0,category="economic"):
    try:prices=await availability.product_countries(product)
    except FiveSimError as exc:await safe_edit(call,humanize(exc),kb.back_to("buy"));return
    if not prices:await safe_edit(call,texts.NO_NUMBERS,kb.back_to("buy"));return
    countries=await fivesim.countries_safe();rate,profit=await _pricing();items=[(country,calc_price(cost,rate,profit)) for country,(_,cost,_) in prices.items()];items.sort(key=lambda x:x[1]);pages=max(1,math.ceil(len(items)/PAGE_SIZE));page=min(max(0,page),pages-1);chunk=items[page*PAGE_SIZE:(page+1)*PAGE_SIZE];buttons=[(country_title(c,countries),f"{price:,} تومان",f"cn:{product}:{c}:{category}") for c,price in chunk];text=f"<b>{service_title(product)}</b>\n\n{'خرید اقتصادی' if category=='economic' else 'خرید اختصاصی'}\nکشور را انتخاب کنید.\nصفحه {page+1} از {pages}";await safe_edit(call,text,kb.countries_kb(product,buttons,page,pages))
@router.callback_query(F.data.startswith("srv:"))
async def cb_service(call:CallbackQuery):
    try:parts=call.data.split(":");product=parts[1];page=int(parts[2]);category=parts[3] if len(parts)>3 else "economic"
    except (ValueError,IndexError):await call.answer();return
    if not await sales_allowed():await call.answer("فروش موقتاً غیرفعال است.",show_alert=True);return
    await call.answer("در حال دریافت فهرست...");await _loading(call,["دریافت فهرست ▓░░░","محاسبه قیمت‌ها ▓▓░░","آماده‌سازی ▓▓▓▓"]);await _show_countries(call,product,page,category)
@router.callback_query(F.data.startswith("cn:"))
async def cb_country(call:CallbackQuery):
    try:parts=call.data.split(":");product,country=parts[1],parts[2]
    except (ValueError,IndexError):await call.answer();return
    try:values=await availability.country_options(product,country)
    except FiveSimError as exc:await call.answer(humanize(exc),show_alert=True);return
    chosen=fivesim.choose_operator(values,country,product,await _preferred_operators())
    if not chosen:await call.answer(SOLD_OUT,show_alert=True);return
    operator,cost,count=chosen;rate,profit=await _pricing();price=calc_price(cost,rate,profit);user=await db.get_user(call.from_user.id);balance=user["balance"] if user else 0;await safe_edit(call,texts.CONFIRM.format(service=service_title(product),country=country_title(country,await fivesim.countries_safe()),count=count,price=price,balance=balance,note=texts.NOTE_OK if balance>=price else texts.NOTE_LOW),kb.confirm_kb(product,country,operator,balance>=price));await call.answer()
@router.callback_query(F.data.startswith("legacy_ok:"))
async def legacy_purchase_disabled(call:CallbackQuery):await call.answer("این پیش‌فاکتور منقضی شده؛ دوباره شماره را انتخاب کنید.",show_alert=True)
async def _own_order(call):
    try:order=await db.get_order(int(call.data.split(":")[1]))
    except (ValueError,IndexError):return None
    return order if order and order["user_id"]==call.from_user.id else None
@router.callback_query(F.data.startswith("chk:"))
async def cb_check(call:CallbackQuery):
    order=await _own_order(call)
    if not order:await call.answer("سفارش پیدا نشد.",show_alert=True);return
    if order["status"] in ("CANCELED","TIMEOUT"):await call.answer("مبلغ قبلاً برگشت خورده.",show_alert=True);return
    try:result=await sync_order(call.bot,order,notify=False)
    except FiveSimError as exc:await call.answer(humanize(exc),show_alert=True);return
    if result["status"] in ("RECEIVED","FINISHED") and (result.get("code") or result.get("text")):await call.answer("کد تأیید دریافت شد!");await safe_edit(call,code_message(order,result.get("code") or "",result.get("text") or ""),kb.order_received_kb(order["id"]) if result["status"]=="RECEIVED" else kb.back_main())
    elif result["status"]=="TIMEOUT":await call.answer("سفارش بسته شد و مبلغ برگشت خورد.",show_alert=True);await safe_edit(call,texts.REFUNDED.format(order_id=order["id"],phone=phone_ltr(order["phone"]),price=order["price"],reason=texts.REASON_TIMEOUT),kb.back_main())
    else:await call.answer(texts.WAITING_CODE,show_alert=True)
@router.callback_query(F.data.startswith("cnl:"))
async def cb_cancel(call:CallbackQuery):
    order=await _own_order(call)
    if not order:await call.answer("سفارش پیدا نشد.",show_alert=True);return
    if order["status"]!="PENDING":await call.answer("این سفارش قابل لغو نیست.",show_alert=True);return
    try:await FiveSimClient(await db.get_setting("fivesim_api")).cancel(order["fivesim_id"])
    except FiveSimError as exc:await call.answer(humanize(exc),show_alert=True);return
    if await refund(call.bot,order,"CANCELED",texts.REASON_USER,notify=False):await call.answer("لغو شد و مبلغ برگشت خورد.");await safe_edit(call,texts.REFUNDED.format(order_id=order["id"],phone=phone_ltr(order["phone"]),price=order["price"],reason=texts.REASON_USER),kb.back_main())
@router.callback_query(F.data.startswith("fin:"))
async def cb_finish(call:CallbackQuery):
    order=await _own_order(call)
    if not order:await call.answer("سفارش پیدا نشد.",show_alert=True);return
    if order["status"]=="RECEIVED":
        try:await FiveSimClient(await db.get_setting("fivesim_api")).finish(order["fivesim_id"])
        except FiveSimError:pass
        await db.transition_order(order["id"],("RECEIVED",),"FINISHED")
    await call.answer("سفارش تکمیل شد");await safe_edit(call,texts.ORDER_FINISHED.format(order_id=order["id"]),kb.back_main())
