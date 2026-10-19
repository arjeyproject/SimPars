"""خرید خدمات شبکه‌های اجتماعی از کاتالوگ تأییدشده پنلیکس."""
from __future__ import annotations
import asyncio,logging
from collections import defaultdict
from aiogram import F,Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State,StatesGroup
from aiogram.types import CallbackQuery,Message
import database as db
import keyboards as kb
from services.sintel_catalog import PLATFORM_LABELS,calculate_order_price,category_label,get_cached_catalog,get_catalog_by_subcategory,get_service_by_id
from services.sintel_orders import OrderResult,create_sintel_order,format_order_status_text,get_order_status_from_provider,get_sintel_order,get_user_sintel_orders
from services.market import sales_allowed
from utils import esc,safe_edit
router=Router(); log=logging.getLogger(__name__); _locks:dict[int,asyncio.Lock]=defaultdict(asyncio.Lock)
class SintelStates(StatesGroup): link=State(); quantity=State()
async def _pricing(service:dict,quantity:int)->tuple[int,int]:
    profit=await db.get_setting("panelix_profit_percent") or await db.get_setting("profit_percent"); fx=await db.get_float("rate",0) if str(service.get("currency","" )).upper()=="USD" else 0
    cost=calculate_order_price(service["rate"],quantity,unit=service.get("rate_unit",""),currency=service.get("currency",""),fx_rate=fx); return cost,int(cost*(1+float(profit or 0)/100)) if cost else 0
def _catalog_markup(platforms:list[str]):
    rows=[]
    for i in range(0,len(platforms),2): rows.append([kb.btn(f"{PLATFORM_LABELS.get(p,("📱",p))[0]} {PLATFORM_LABELS.get(p,("📱",p))[1]}",f"stsc:{p}:all",style=("danger" if i//2%2==0 else "success")) for p in platforms[i:i+2]])
    return kb.markup(rows+[ [kb.btn("🏠 منوی اصلی","home",style="primary")] ])
@router.callback_query(F.data=="sintel")
async def main(call:CallbackQuery):
    if not await db.get_setting("panelix_api"):await call.answer("❌ خدمات فعلاً آماده نیست.",show_alert=True);return
    services=await get_cached_catalog()
    if not services:await call.answer("❌ فهرست خدمات آماده نیست.",show_alert=True);return
    platforms=sorted({s["platform"] for s in services},key=lambda p:list(PLATFORM_LABELS).index(p) if p in PLATFORM_LABELS else 99)
    await safe_edit(call,"📣 <b>خدمات شبکه‌های اجتماعی</b>\n\nیکی از شبکه‌ها را انتخاب کنید.",_catalog_markup(platforms));await call.answer()
@router.callback_query(F.data.startswith("stsc:"))
async def category(call:CallbackQuery):
    _,platform,_=call.data.split(":",2); services=await get_cached_catalog(platform); groups=sorted({s["subcategory"] for s in services})
    if not groups:await call.answer("❌ خدمتی در این بخش نیست.",show_alert=True);return
    rows=[]
    for i in range(0,len(groups),2): rows.append([kb.btn(f"📦 {category_label(platform,g)}",f"stgroup:{platform}:{g}",style=("danger" if i//2%2==0 else "success")) for g in groups[i:i+2]])
    await safe_edit(call,"🗂 <b>دسته خدمات</b>\n\nیک دسته را انتخاب کنید.",kb.markup(rows+[kb._social_back("sintel")]));await call.answer()
@router.callback_query(F.data.startswith("stgroup:"))
async def services(call:CallbackQuery):
    _,platform,group=call.data.split(":",2); items=await get_catalog_by_subcategory(platform,group)
    if not items:await call.answer("❌ خدمتی با قیمت تأییدشده پیدا نشد.",show_alert=True);return
    await safe_edit(call,"📦 <b>خدمات موجود</b>\n\nخدمت موردنظر را انتخاب کنید.",kb.sintel_services_list(items));await call.answer()
@router.callback_query(F.data.startswith("stlg:"))
async def select_service(call:CallbackQuery,state:FSMContext):
    try:sid=int(call.data.split(":",1)[1])
    except (ValueError,IndexError):await call.answer();return
    service=await get_service_by_id(sid)
    if not service:await call.answer("❌ این خدمت دیگر فعال نیست.",show_alert=True);return
    await state.update_data(sintel_service_id=sid);await state.set_state(SintelStates.link);await safe_edit(call,f"🧾 <b>{esc(service.get('display_name') or service['name'])}</b>\n\n🔗 لینک یا آیدی هدف را ارسال کنید.",kb.cancel_kb("sintel"));await call.answer()
@router.message(SintelStates.link)
async def link(message:Message,state:FSMContext):
    value=(message.text or "").strip()
    if len(value)<2:await message.answer("❌ لینک یا آیدی هدف معتبر نیست.");return
    await state.update_data(sintel_link=value);await state.set_state(SintelStates.quantity);data=await state.get_data();service=await get_service_by_id(int(data["sintel_service_id"]))
    if not service:await message.answer("❌ این خدمت دیگر فعال نیست.",reply_markup=kb.back_main());await state.clear();return
    await message.answer(f"🔢 تعداد موردنظر را وارد کنید.\nمحدوده: <b>{service['min_quantity']:,}</b> تا <b>{service['max_quantity']:,}</b>",reply_markup=kb.cancel_kb("sintel"))
@router.message(SintelStates.quantity)
async def quantity(message:Message,state:FSMContext):
    try:value=int((message.text or "").replace(","," ").replace("٬","").replace(" ",""))
    except ValueError:await message.answer("❌ تعداد باید عدد باشد.");return
    data=await state.get_data();service=await get_service_by_id(int(data.get("sintel_service_id",0))) if data.get("sintel_service_id") else None
    if not service or not service["price_verified"]:await message.answer("❌ قیمت این خدمت قابل تأیید نیست.");return
    if not service["min_quantity"]<=value<=service["max_quantity"]:await message.answer(f"❌ تعداد باید بین {service['min_quantity']:,} و {service['max_quantity']:,} باشد.");return
    if not await sales_allowed():await message.answer("❌ خرید موقتاً متوقف است.");return
    cost,price=await _pricing(service,value)
    if not price:await message.answer("❌ قیمت نهایی قابل تأیید نیست.");return
    user=await db.get_user(message.from_user.id);balance=int(user["balance"]) if user else 0;await state.update_data(sintel_quantity=value,sintel_provider_cost=cost,sintel_selling_price=price)
    await message.answer(f"🧾 <b>پیش‌فاکتور</b>\n\n🔌 {esc(service.get('display_name') or service['name'])}\n🔗 <code>{esc(data['sintel_link'])}</code>\n📦 تعداد: <b>{value:,}</b>\n💰 مبلغ: <b>{price:,} تومان</b>\n👛 موجودی: <b>{balance:,} تومان</b>\n\nقیمت هنگام تأیید دوباره بررسی می‌شود.",reply_markup=kb.sintel_confirm_kb(balance>=price))
@router.callback_query(F.data=="sintel_buy")
async def buy(call:CallbackQuery,state:FSMContext):
    lock=_locks[call.from_user.id]
    if lock.locked():await call.answer("⏳ درخواست قبلی در حال پردازش است.",show_alert=True);return
    async with lock:
        data=await state.get_data();service=await get_service_by_id(int(data.get("sintel_service_id",0))) if data.get("sintel_service_id") else None
        if not service:await call.answer("❌ این خدمت دیگر فعال نیست.",show_alert=True);return
        cost,price=await _pricing(service,int(data["sintel_quantity"]))
        if not price:await call.answer("❌ قیمت قابل تأیید نیست.",show_alert=True);return
        result:OrderResult=await create_sintel_order(call.from_user.id,service["service_id"],data["sintel_link"],int(data["sintel_quantity"]),cost,price)
    await state.clear()
    if not result.success:await call.answer(result.error or "❌ سفارش انجام نشد.",show_alert=True);return
    await call.answer("✅ سفارش ثبت شد");await safe_edit(call,f"✅ <b>سفارش ثبت شد</b>\n\n🆔 سفارش: <code>#{result.order_id}</code>\n💰 مبلغ: <b>{price:,} تومان</b>",kb.sintel_order_detail_kb(result.order_id,"PENDING"))
@router.callback_query(F.data=="sintel_orders")
async def orders(call:CallbackQuery):
    items=await get_user_sintel_orders(call.from_user.id,20);text="📦 <b>سفارش‌های خدمات شما</b>\n\n" if items else "📭 هنوز سفارشی ثبت نکرده‌اید."
    for item in items:text+=f"🆔 <code>#{item['id']}</code> | {item['quantity']:,} | {format_order_status_text(item['status'])}\n"
    await safe_edit(call,text,kb.sintel_orders_kb());await call.answer()
@router.callback_query(F.data.startswith("stch:"))
async def check(call:CallbackQuery):
    try:oid=int(call.data.split(":",1)[1])
    except (ValueError,IndexError):await call.answer();return
    order=await get_sintel_order(oid)
    if not order or order["user_id"]!=call.from_user.id:await call.answer("❌ سفارش پیدا نشد.",show_alert=True);return
    status=await get_order_status_from_provider(oid);text=f"🔄 <b>وضعیت سفارش #{oid}</b>\n\n📊 {format_order_status_text(status.status)}"
    if status.remains:text+=f"\n⏳ باقیمانده: {status.remains:,}"
    if status.error:text+=f"\n⚠️ {esc(status.error)}"
    await safe_edit(call,text,kb.sintel_order_detail_kb(oid,status.status));await call.answer()
@router.callback_query(F.data=="sintel_wallet")
async def wallet(call:CallbackQuery):await call.answer();await safe_edit(call,"💰 برای ادامه، کیف پول را شارژ کنید.",kb.back_to("wallet"))
