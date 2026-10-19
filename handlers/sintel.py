"""خرید خدمات شبکه‌های اجتماعی از کاتالوگ زنده پنلیکس."""
from __future__ import annotations
import asyncio, logging
from collections import defaultdict
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
import database as db
import keyboards as kb
from services.sintel_catalog import PLATFORM_LABELS, calculate_order_price, category_label, get_cached_catalog, get_catalog_by_subcategory, get_service_by_id
from services.sintel_orders import OrderResult, create_sintel_order, format_order_status_text, get_order_status_from_provider, get_sintel_order, get_user_sintel_orders
from services.market import sales_allowed
from utils import esc, safe_edit

router = Router(); log = logging.getLogger(__name__); _locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
class SintelStates(StatesGroup): link = State(); quantity = State()

async def _pricing(service: dict, quantity: int) -> tuple[int, int]:
    profit = await db.get_setting("panelix_profit_percent") or await db.get_setting("profit_percent")
    fx = await db.get_float("rate", 0) if str(service.get("currency","")).upper() == "USD" else 0
    cost = calculate_order_price(service["rate"], quantity, unit=service.get("rate_unit", ""), currency=service.get("currency", ""), fx_rate=fx)
    return cost, int(cost * (1 + float(profit or 0) / 100)) if cost else 0

def _catalog_markup(platforms: list[str]):
    rows=[]
    for p in platforms:
        e,t=PLATFORM_LABELS.get(p,("📱",p)); rows.append([kb.btn(f"{e} {t}",f"stsc:{p}:all",style="primary")])
    return kb.markup(rows+[[kb.btn("🏠 منوی اصلی","home",style="danger")]])

@router.callback_query(F.data == "sintel")
async def main(call: CallbackQuery):
    if not await db.get_setting("panelix_api"): await call.answer("❌ خدمات شبکه‌های اجتماعی هنوز در مدیریت پنلیکس تنظیم نشده است.", show_alert=True); return
    services = await get_cached_catalog()
    if not services: await call.answer("❌ کاتالوگ آماده نیست؛ مدیر باید فهرست سرویس‌ها را دریافت کند.", show_alert=True); return
    platforms = sorted({s["platform"] for s in services}, key=lambda p: list(PLATFORM_LABELS).index(p) if p in PLATFORM_LABELS else 99)
    await safe_edit(call,"📣 <b>خدمات شبکه‌های اجتماعی</b>\n\nشبکه و دسته خدمات را انتخاب کنید:",_catalog_markup(platforms)); await call.answer()

@router.callback_query(F.data.startswith("stsc:"))
async def category(call: CallbackQuery):
    _, platform, _ = call.data.split(":",2); services=await get_cached_catalog(platform)
    groups=sorted({s["subcategory"] for s in services})
    if not groups: await call.answer("❌ سرویس فعالی در این بخش نیست.",show_alert=True); return
    rows=[]
    for group in groups:
        label=category_label(platform,group); rows.append([kb.btn(f"📦 {label}",f"stgroup:{platform}:{group}",style="primary")])
    await safe_edit(call,"🗂 <b>دسته‌بندی خدمات</b>\n\nدسته موردنظر را انتخاب کنید:",kb.markup(rows+[[kb.btn("🔙 بازگشت","sintel",style="danger")],[kb.btn("🏠 منوی اصلی","home",style="danger")]])); await call.answer()

@router.callback_query(F.data.startswith("stgroup:"))
async def services(call: CallbackQuery):
    _, platform, group = call.data.split(":",2); items=await get_catalog_by_subcategory(platform,group)
    if not items: await call.answer("❌ سرویسی با قیمت تأییدشده موجود نیست.",show_alert=True); return
    await safe_edit(call,"📦 <b>سرویس‌های موجود</b>\n\nقیمت و محدودیت‌ها در مرحله بعد نمایش داده می‌شود:",kb.sintel_services_list(items)); await call.answer()

@router.callback_query(F.data.startswith("stlg:"))
async def select_service(call: CallbackQuery,state:FSMContext):
    try: sid=int(call.data.split(":",1)[1])
    except (ValueError,IndexError): await call.answer(); return
    service=await get_service_by_id(sid)
    if not service: await call.answer("❌ سرویس غیرفعال یا نیازمند تأیید قیمت است.",show_alert=True); return
    await state.update_data(sintel_service_id=sid)
    text=(f"🧾 <b>{esc(service.get('display_name') or service['name'])}</b>\n\n" f"🆔 شناسه پنلیکس: <code>{sid}</code>\n" f"📦 حداقل: <b>{service['min_quantity']:,}</b> | حداکثر: <b>{service['max_quantity']:,}</b>\n" f"📝 {esc(service.get('description') or 'توضیحات ارائه‌دهنده ثبت نشده است.')}\n\n🔗 نشانی هدف را بفرستید:")
    await state.set_state(SintelStates.link); await safe_edit(call,text,kb.cancel_kb("sintel")); await call.answer()

@router.message(SintelStates.link)
async def link(message: Message,state:FSMContext):
    value=(message.text or "").strip()
    if len(value)<2: await message.answer("❌ نشانی هدف معتبر نیست."); return
    await state.update_data(sintel_link=value); await state.set_state(SintelStates.quantity)
    data=await state.get_data(); service=await get_service_by_id(int(data["sintel_service_id"]))
    if not service: await message.answer("❌ سرویس دیگر در دسترس نیست.",reply_markup=kb.back_main()); await state.clear(); return
    await message.answer(f"📦 تعداد را وارد کنید: از <b>{service['min_quantity']:,}</b> تا <b>{service['max_quantity']:,}</b>",reply_markup=kb.cancel_kb("sintel"))

@router.message(SintelStates.quantity)
async def quantity(message: Message,state:FSMContext):
    try: value=int((message.text or "").replace(","," ").replace("٬","").replace(" ",""))
    except ValueError: await message.answer("❌ تعداد باید عدد باشد."); return
    data=await state.get_data(); service=await get_service_by_id(int(data["sintel_service_id"]))
    if not service or not service["price_verified"]: await message.answer("❌ قیمت این سرویس قابل تأیید نیست؛ خرید متوقف شد."); return
    if not service["min_quantity"]<=value<=service["max_quantity"]: await message.answer(f"❌ تعداد باید بین {service['min_quantity']:,} و {service['max_quantity']:,} باشد."); return
    if not await sales_allowed(): await message.answer("❌ نرخ تبدیل معتبر نیست؛ خرید موقتاً متوقف است."); return
    cost, price=await _pricing(service,value)
    if not price: await message.answer("❌ قیمت نهایی قابل تأیید نیست؛ خرید متوقف شد."); return
    user=await db.get_user(message.from_user.id); balance=int(user["balance"]) if user else 0
    await state.update_data(sintel_quantity=value,sintel_provider_cost=cost,sintel_selling_price=price)
    await message.answer(f"🧾 <b>پیش‌فاکتور</b>\n\n🔌 سرویس: {esc(service.get('display_name') or service['name'])}\n🔗 هدف: <code>{esc(data['sintel_link'])}</code>\n📦 تعداد: <b>{value:,}</b>\n💰 مبلغ: <b>{price:,} تومان</b>\n👛 موجودی: <b>{balance:,} تومان</b>\n\n⚠️ قیمت در لحظه تأیید دوباره بررسی می‌شود.",reply_markup=kb.sintel_confirm_kb(balance>=price))

@router.callback_query(F.data == "sintel_buy")
async def buy(call: CallbackQuery,state:FSMContext):
    lock=_locks[call.from_user.id]
    if lock.locked(): await call.answer("⏳ درخواست قبلی در حال پردازش است.",show_alert=True); return
    async with lock:
        data=await state.get_data(); service=await get_service_by_id(int(data.get("sintel_service_id",0))) if data.get("sintel_service_id") else None
        if not service: await call.answer("❌ سرویس دیگر موجود نیست.",show_alert=True); return
        cost,price=await _pricing(service,int(data["sintel_quantity"]))
        if not price: await call.answer("❌ قیمت تأییدنشده است.",show_alert=True); return
        result:OrderResult=await create_sintel_order(call.from_user.id,service["service_id"],data["sintel_link"],int(data["sintel_quantity"]),cost,price)
    await state.clear()
    if not result.success: await call.answer(result.error or "❌ سفارش ثبت نشد.",show_alert=True); return
    await call.answer("✅ سفارش ثبت شد")
    await safe_edit(call,f"✅ <b>سفارش پنلیکس ثبت شد</b>\n\n🆔 سفارش داخلی: <code>#{result.order_id}</code>\n🆔 سفارش پنلیکس: <code>{esc(result.provider_order_id or '')}</code>\n💰 مبلغ: <b>{price:,} تومان</b>",kb.sintel_order_detail_kb(result.order_id,"PENDING"))

@router.callback_query(F.data == "sintel_orders")
async def orders(call: CallbackQuery):
    items=await get_user_sintel_orders(call.from_user.id,20)
    text="📦 <b>سفارش‌های خدمات شما</b>\n\n" if items else "📭 هنوز سفارشی ثبت نکرده‌اید."
    for item in items: text+=f"🆔 <code>#{item['id']}</code> | {item['quantity']:,} واحد | {format_order_status_text(item['status'])}\n"
    await safe_edit(call,text,kb.sintel_orders_kb()); await call.answer()

@router.callback_query(F.data.startswith("stch:"))
async def check(call: CallbackQuery):
    try: oid=int(call.data.split(":",1)[1])
    except (ValueError,IndexError): await call.answer(); return
    order=await get_sintel_order(oid)
    if not order or order["user_id"]!=call.from_user.id: await call.answer("❌ سفارش پیدا نشد.",show_alert=True); return
    status=await get_order_status_from_provider(oid)
    text=f"🔄 <b>وضعیت سفارش #{oid}</b>\n\n📊 {format_order_status_text(status.status)}"
    if status.remains: text+=f"\n⏳ باقیمانده: {status.remains:,}"
    if status.error: text+=f"\n⚠️ {esc(status.error)}"
    await safe_edit(call,text,kb.sintel_order_detail_kb(oid,status.status)); await call.answer()

@router.callback_query(F.data == "sintel_wallet")
async def wallet(call: CallbackQuery): await call.answer(); await safe_edit(call,"💰 برای ادامه، کیف پول را شارژ کنید.",kb.back_to("wallet"))
