"""Live storefront catalog with price, availability, country and operator categories."""
from __future__ import annotations
from aiogram import F, Router
from aiogram.types import CallbackQuery
import database as db
import keyboards as kb
from services import fivesim
from services.fivesim import FiveSimError,humanize
from services.market import sales_allowed
import texts
router=Router(); MAX_PRODUCTS=200

def _products(catalog,category):
    products=[]
    for product,countries in catalog.items():
        if not countries or len(product)>40: continue
        total=sum(item[2] for item in countries.values()); lowest=min((item[1] for item in countries.values()),default=999999)
        products.append((product,total,lowest))
    if category=="cheap": products.sort(key=lambda x:(x[2],-x[1]))
    elif category=="economic": products.sort(key=lambda x:(-x[1],x[2]))
    else: products.sort(key=lambda x:(0 if x[0] in texts.SERVICE_MAP else 1,x[0].lower()))
    return [p[0] for p in products[:MAX_PRODUCTS]]

@router.callback_query(F.data=="buy")
async def live_buy_menu(call:CallbackQuery):
    if not await db.get_setting("fivesim_api"):
        await call.answer("🔑 اتصال فروشگاه هنوز در پنل مدیریت تنظیم نشده است.",show_alert=True); return
    if not await sales_allowed():
        await call.answer("⛔️ فروش موقتاً متوقف است؛ نرخ قیمت‌گذاری را در پنل مدیریت بررسی کن.",show_alert=True); return
    await call.answer("⏳ در حال آماده‌سازی فروشگاه...")
    try: catalog=await fivesim.get_all_prices()
    except FiveSimError as exc: await call.message.edit_text(humanize(exc),reply_markup=kb.back_main()); return
    if not catalog: await call.message.edit_text(texts.NO_NUMBERS,reply_markup=kb.back_main()); return
    await call.message.edit_text("🛍 <b>فروشگاه سیم‌پارس</b>\n\n✨ داده‌های زنده موجودی و قیمت آماده شد.\n\n💎 ارزان‌ترین گزینه‌ها\n💰 شماره‌های اقتصادی\n🌍 همه کشورها و اپراتورهای موجود\n\n👇 دسته‌بندی را انتخاب کن:",reply_markup=kb.storefront_kb(list(catalog)))

@router.callback_query(F.data.startswith("cat:"))
async def catalog_category(call:CallbackQuery):
    category=call.data.split(":",1)[1]
    try: catalog=await fivesim.get_all_prices()
    except FiveSimError as exc: await call.message.edit_text(humanize(exc),reply_markup=kb.back_main()); return
    products=_products(catalog,category)
    title={"cheap":"💎 ارزان‌ترین گزینه‌ها","economic":"💰 شماره‌های اقتصادی","all":"🌍 همه گزینه‌های فعال"}.get(category,"🌍 همه گزینه‌ها")
    await call.message.edit_text(f"{title}\n\n📍 کشورها با پرچم و قیمت مرتب شده‌اند.\n📡 در مرحله بعد همه اپراتورهای دارای موجودی و قیمت جداگانه نمایش داده می‌شوند.\n\n👇 سرویس را انتخاب کن:",reply_markup=kb.product_kb(products,category))
