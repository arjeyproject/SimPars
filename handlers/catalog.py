"""Live storefront catalog: platform selection always comes before countries."""
from __future__ import annotations
from aiogram import F, Router
from aiogram.types import CallbackQuery
import database as db
import keyboards as kb
from services import fivesim
from services.fivesim import FiveSimError, humanize
from services.market import sales_allowed
from utils import safe_edit
import texts
router = Router(); MAX_PRODUCTS = 200; PRODUCT_PAGE_SIZE = 12
PRIORITY = {"telegram": 0, "instagram": 1, "whatsapp": 2, "openai": 3, "google": 4, "tiktok": 5, "facebook": 6, "twitter": 7, "discord": 8}
PLATFORM_PAGE = "🛍 <b>خرید شماره مجازی</b>\n\n📱 <b>ابتدا برنامه را انتخاب کنید</b>\n\n✈️ تلگرام، 📸 اینستاگرام، 💚 واتساپ و سایر برنامه‌های موجود از سرویس فروش نمایش داده می‌شوند.\n⚡️ بعد از انتخاب برنامه، در صفحه بعد فقط کشورهای دارای موجودی و قیمت لحظه‌ای نشان داده می‌شود.\nصفحه {page} از {pages}\n\n👇 نام برنامه را انتخاب کنید:"

def _product_key(value):
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

def _products(catalog, category):
    """Return provider products only, never country keys from a reversed payload."""
    products=[]
    supported=set(texts.SERVICE_MAP)
    for product, countries in (catalog or {}).items():
        key=_product_key(product)
        # The 5SIM storefront supports the service names declared by the bot.
        # Reject country-shaped/unknown keys so they cannot appear as platforms.
        if key not in supported or not isinstance(countries, dict) or not countries: continue
        costs=[item[1] for item in countries.values() if isinstance(item,(tuple,list)) and len(item)>1]
        stocks=[item[2] for item in countries.values() if isinstance(item,(tuple,list)) and len(item)>2]
        if not costs: continue
        total=sum(stocks); lowest=min(costs,default=999999); highest=max(costs,default=0); products.append((key,total,lowest,highest))
    if category=="economic": products.sort(key=lambda x:(PRIORITY.get(x[0],99),x[2],-x[1]))
    elif category=="exclusive": products.sort(key=lambda x:(PRIORITY.get(x[0],99),-x[3],-x[1]))
    else: products.sort(key=lambda x:(PRIORITY.get(x[0],99),x[2],x[0]))
    return [p[0] for p in products[:MAX_PRODUCTS]]
async def _show_platforms(call:CallbackQuery,category="economic",page=0):
    try: catalog=await fivesim.get_all_prices()
    except FiveSimError as exc: await safe_edit(call,humanize(exc),kb.back_main()); return
    products=_products(catalog,category)
    if not products: await safe_edit(call,"😕 هیچ برنامهٔ پشتیبانی‌شده‌ای در حال حاضر موجود نیست.\n\nلطفاً کمی بعد دوباره تلاش کن.",kb.back_main()); return
    pages=max(1,(len(products)+PRODUCT_PAGE_SIZE-1)//PRODUCT_PAGE_SIZE); page=min(max(0,page),pages-1); chunk=products[page*PRODUCT_PAGE_SIZE:(page+1)*PRODUCT_PAGE_SIZE]
    await safe_edit(call,PLATFORM_PAGE.format(page=page+1,pages=pages),kb.platforms_kb(chunk,category,page,pages))
@router.callback_query(F.data=="buy")
async def live_buy_menu(call:CallbackQuery):
    if not await db.get_setting("fivesim_api"): await call.answer("اتصال فروشگاه در پنل مدیریت تنظیم نشده است.",show_alert=True); return
    if not await sales_allowed(): await call.answer("فروش موقتاً متوقف است؛ نرخ را در پنل مدیریت بررسی کن.",show_alert=True); return
    await call.answer("در حال آماده‌سازی فهرست برنامه‌ها...")
    await _show_platforms(call,"economic",0)
@router.callback_query(F.data.startswith("cat:"))
async def catalog_category(call:CallbackQuery):
    parts=call.data.split(":"); category=parts[1] if len(parts)>1 else "economic"; page=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 0
    await _show_platforms(call,category,page); await call.answer()
