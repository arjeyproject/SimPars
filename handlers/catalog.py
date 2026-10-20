"""Live storefront catalog: platforms first, then country selection."""
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
PRIORITY = {"telegram": 0, "whatsapp": 1, "instagram": 2}
def _products(catalog, category):
    products=[]
    for product, countries in catalog.items():
        if not countries or len(product)>40: continue
        costs=[item[1] for item in countries.values()]; total=sum(item[2] for item in countries.values()); lowest=min(costs,default=999999); highest=max(costs,default=0); products.append((product,total,lowest,highest))
    if category=="economic": products.sort(key=lambda x:(PRIORITY.get(x[0],99),x[2],-x[1]))
    elif category=="exclusive": products.sort(key=lambda x:(PRIORITY.get(x[0],99),-x[3],-x[1]))
    else: products.sort(key=lambda x:(PRIORITY.get(x[0],99),x[2],x[0].lower()))
    return [p[0] for p in products[:MAX_PRODUCTS]]
@router.callback_query(F.data=="buy")
async def live_buy_menu(call:CallbackQuery):
    if not await db.get_setting("fivesim_api"): await call.answer("اتصال فروشگاه در پنل مدیریت تنظیم نشده است.",show_alert=True); return
    if not await sales_allowed(): await call.answer("فروش موقتاً متوقف است؛ نرخ را در پنل مدیریت بررسی کن.",show_alert=True); return
    await call.answer("در حال آماده‌سازی فروشگاه...")
    try: catalog=await fivesim.get_all_prices()
    except FiveSimError as exc: await safe_edit(call,humanize(exc),kb.back_main()); return
    if not catalog: await safe_edit(call,texts.NO_NUMBERS,kb.back_main()); return
    products=_products(catalog,"economic"); pages=max(1,(len(products)+PRODUCT_PAGE_SIZE-1)//PRODUCT_PAGE_SIZE); chunk=products[:PRODUCT_PAGE_SIZE]
    await safe_edit(call,"🛍 <b>خرید شماره مجازی</b>\n\nپلتفرم را انتخاب کن:",kb.product_kb(chunk,"economic",0,pages))
@router.callback_query(F.data.startswith("cat:"))
async def catalog_category(call:CallbackQuery):
    parts=call.data.split(":"); category=parts[1] if len(parts)>1 else "economic"; page=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 0
    try: catalog=await fivesim.get_all_prices()
    except FiveSimError as exc: await safe_edit(call,humanize(exc),kb.back_main()); return
    products=_products(catalog,category); pages=max(1,(len(products)+PRODUCT_PAGE_SIZE-1)//PRODUCT_PAGE_SIZE); page=min(max(0,page),pages-1); chunk=products[page*PRODUCT_PAGE_SIZE:(page+1)*PRODUCT_PAGE_SIZE]
    await safe_edit(call,"🛍 <b>خرید شماره مجازی</b>\n\nپلتفرم را انتخاب کن:",kb.product_kb(chunk,category,page,pages))
