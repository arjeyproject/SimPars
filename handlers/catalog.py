"""Live 5SIM-backed storefront catalog."""
from __future__ import annotations
from aiogram import F, Router
from aiogram.types import CallbackQuery
import database as db
import keyboards as kb
from services import fivesim
from services.fivesim import FiveSimError, humanize
from services.market import sales_allowed
import texts

router = Router()
MAX_PRODUCTS = 40


def _label(product: str) -> str:
    known = texts.SERVICE_MAP.get(product)
    if known: return f"{known[0]} {known[1]}"
    return f"🌐 {product.replace('_', ' ').replace('-', ' ').title()}"[:32]


def _menu(products: list[str]):
    rows, row = [], []
    for product in products:
        row.append(kb.btn(_label(product), f"srv:{product}:0"))
        if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([kb.btn("🏠 منوی اصلی", "home")])
    return kb.markup(rows)


@router.callback_query(F.data == "buy")
async def live_buy_menu(call: CallbackQuery) -> None:
    if not await db.get_setting("fivesim_api") or not await sales_allowed():
        await call.answer(texts.SALES_DISABLED, show_alert=True)
        return
    await call.answer("⏳ دریافت فهرست سرویس‌های فعال از 5Sim...")
    try: catalog = await fivesim.get_all_prices()
    except FiveSimError as exc:
        await call.message.edit_text(humanize(exc), reply_markup=kb.back_main())
        return
    known = [p for p in texts.SERVICE_MAP if p in catalog and len(p) <= 30]
    extras = [p for p in catalog if p not in texts.SERVICE_MAP and len(p) <= 30]
    extras.sort(key=lambda p: (-sum(item[2] for item in catalog[p].values()), p.lower()))
    products = known + extras[: max(0, MAX_PRODUCTS - len(known))]
    if not products:
        await call.message.edit_text(texts.NO_NUMBERS, reply_markup=kb.back_main())
        return
    await call.message.edit_text("🛒 <b>خرید شماره مجازی</b>\n\n📲 سرویس‌ها از موجودی لحظه‌ای 5Sim خوانده می‌شوند؛ سرویس بدون موجودی نمایش داده نمی‌شود.\n\n👇 انتخاب کن:", reply_markup=_menu(products))
