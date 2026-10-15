"""پنل مدیریت سینتل - تنظیمات API و کاتالوگ."""
from __future__ import annotations
import logging
from datetime import datetime
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
import database as db
import keyboards as kb
from config import ADMIN_IDS
from services.sintel import SintelClient, SintelError, _humanize_error, clean_api_key, invalidate_catalog_cache
from services.sintel_catalog import sync_catalog_from_provider
from utils import esc, mask, parse_number, safe_edit
router=Router(); log=logging.getLogger(__name__); router.message.filter(F.from_user.id.in_(ADMIN_IDS)); router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))
class SintelAdminStates(StatesGroup): api_key=State(); profit_percent=State()
def _format_balance(balance): return "⚠️ خطا در دریافت" if balance is None else f"{balance:,.0f} تومان"
async def _get_sintel_status():
    api_key=await db.get_setting("sintel_api"); enabled=await db.get_setting("sintel_enabled"); last_sync=await db.get_setting("sintel_last_sync"); status={"enabled":enabled=="1","api_key_set":bool(api_key),"last_sync":last_sync or "هرگز","balance":None,"service_count":0}
    if api_key:
        try:
            status["balance"]=await SintelClient(api_key).get_balance()
            async with db._db.execute("SELECT COUNT(*) FROM sintel_services WHERE is_active=1") as cur: status["service_count"]=(await cur.fetchone())[0]
        except SintelError as exc: status["error"]=_humanize_error(exc)
    return status
@router.callback_query(F.data=="panel_sintel")
async def cb_sintel_admin(call,state):
    await state.clear(); await call.answer(); status=await _get_sintel_status(); error=f"\n⚠️ {status['error']}" if status.get("error") else ""; text=("🔌 <b>پنل مدیریت سینتل</b>\n\n" f"🔑 API: {'✅ تنظیم شده' if status['api_key_set'] else '❌ تنظیم نشده'}\n" f"🔄 وضعیت: {'✅ فعال' if status['enabled'] else '❌ غیرفعال'}\n" f"💰 موجودی: {_format_balance(status['balance'])}\n" f"📦 سرویس‌ها: {status['service_count']} عدد\n" f"🕐 آخرین همگام‌سازی: <code>{status['last_sync']}</code>\n{error}\n\n👇 عملیات مورد نظر را انتخاب کن:"); await safe_edit(call,text,kb.sintel_admin_menu(status))
@router.callback_query(F.data=="sintel_set_api")
async def cb_sintel_set_api(call,state):
    await state.set_state(SintelAdminStates.api_key); current=await db.get_setting("sintel_api"); shown=mask(current) if current else "—"; await safe_edit(call,"🔑 <b>تنظیم کلید API سینتل</b>\n\n" f"🔑 کلید فعلی: <code>{shown}</code>\n\n📝 فقط خود کلید را ارسال کن، بدون لینک و بدون کلمه Bearer.\n🔒 پیام کلید بعد از اعتبارسنجی حذف می‌شود.",kb.cancel_kb("panel_sintel")); await call.answer()
@router.message(SintelAdminStates.api_key)
async def msg_sintel_api_key(message:Message,state:FSMContext):
    api_key=clean_api_key(message.text or "")
    if not api_key:
        await message.answer("❌ کلید خالی است. فقط خود API Key را بفرست."); return
    try:
        balance=await SintelClient(api_key).get_balance()
    except SintelError as exc:
        await message.answer("❌ <b>کلید سینتل تأیید نشد</b>\n\n" f"{esc(_humanize_error(exc))}\n\nکلید را از پنل سینتل دوباره کپی کن و فقط خود کلید را بفرست.",reply_markup=kb.cancel_kb("panel_sintel")); return
    except Exception as exc:
        log.exception("Sintel API validation failed")
        await message.answer("❌ <b>خطای غیرمنتظره در اتصال به سینتل</b>\n\n" f"{esc(str(exc)[:180])}",reply_markup=kb.cancel_kb("panel_sintel")); return
    await db.set_setting("sintel_api",api_key); invalidate_catalog_cache()
    try: await message.delete()
    except Exception: pass
    await state.clear(); await message.answer("✅ <b>API سینتل با موفقیت ثبت شد.</b>\n\n" f"💰 موجودی پنل: <b>{balance:,.0f} تومان</b>\n\nحالا «همگام‌سازی کاتالوگ» را بزن.",reply_markup=kb.sintel_admin_back())
@router.callback_query(F.data=="sintel_test_connection")
async def cb_sintel_test(call):
    await call.answer("⏳ در حال تست..."); key=await db.get_setting("sintel_api")
    if not key: await call.answer("❌ کلید API تنظیم نشده.",show_alert=True); return
    try: balance=await SintelClient(key).get_balance(); await call.answer(f"✅ اتصال موفق! موجودی: {balance:,.0f} تومان",show_alert=True)
    except SintelError as exc: await call.answer(_humanize_error(exc),show_alert=True)
@router.callback_query(F.data=="sintel_sync_catalog")
async def cb_sintel_sync(call):
    await call.answer("⏳ در حال همگام‌سازی..."); key=await db.get_setting("sintel_api")
    if not key: await call.answer("❌ کلید API تنظیم نشده.",show_alert=True); return
    await safe_edit(call,"🔄 <b>در حال همگام‌سازی کاتالوگ...</b>",None); result=await sync_catalog_from_provider(key)
    if result.get("success"): await db.set_setting("sintel_last_sync",datetime.now().strftime("%Y-%m-%d %H:%M")); text="✅ <b>کاتالوگ همگام شد.</b>\n\n" f"📊 کل: {result.get('total',0)}\n👥 تلگرام: {result.get('telegram',0)}\n📸 اینستاگرام: {result.get('instagram',0)}"
    else:text="❌ <b>همگام‌سازی ناموفق</b>\n\n"+str(result.get("error","خطای نامشخص"))
    await safe_edit(call,text,kb.sintel_admin_back())
