"""پنل کاملاً فارسی مدیریت پنلیکس."""
from __future__ import annotations
import json, logging, time
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
import database as db
import keyboards as kb
from config import ADMIN_IDS
from services.sintel import PanelixClient, PanelixError, _humanize_error, clean_api_key
from services.sintel_catalog import sync_catalog_from_provider
from utils import esc, mask, parse_number, safe_edit

router = Router(); log = logging.getLogger(__name__)
router.message.filter(F.from_user.id.in_(ADMIN_IDS)); router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

class PanelixAdminStates(StatesGroup):
    api_key = State(); setting = State()

async def _status() -> dict:
    key = await db.get_setting("panelix_api"); count = active = 0
    async with db._db.execute("SELECT COUNT(*),COALESCE(SUM(is_active),0) FROM sintel_services WHERE provider='panelix'") as cur:
        row = await cur.fetchone(); count, active = (row or (0,0))
    return {"key": bool(key), "count": count, "active": active, "last": await db.get_setting("panelix_last_sync") or "هرگز", "result": await db.get_setting("panelix_last_sync_result") or "", "unit": await db.get_setting("panelix_rate_unit"), "currency": await db.get_setting("panelix_currency"), "interval": await db.get_setting("panelix_sync_interval")}

def _result_line(result: str) -> str:
    try:
        r = json.loads(result); return f"جدید: {r.get('new',0)} | تغییر نرخ/اطلاعات: {r.get('updated',0)} | غیرفعال: {r.get('unavailable',0)}"
    except (TypeError, ValueError): return "—"

async def _render(call: CallbackQuery) -> None:
    s = await _status(); key = await db.get_setting("panelix_api")
    balance = "—"
    if key:
        try:
            data = await PanelixClient(key).get_balance(); balance = f"{float(data.get('balance',0)):,.4f} {data.get('currency','نامشخص')}"
        except Exception: balance = "⚠️ خطا در دریافت"
    text = ("⚙️ <b>مدیریت پنلیکس</b>\n\n" f"🔑 کلید API: {'✅ تنظیم شده' if s['key'] else '❌ تنظیم نشده'}\n" f"🔌 اتصال: {'✅ قابل بررسی' if s['key'] else '❌ بدون کلید'}\n" f"💰 موجودی پنلیکس: <b>{esc(balance)}</b>\n" f"📦 کل سرویس‌ها: <b>{s['count']:,}</b> | فعال: <b>{s['active']:,}</b>\n" f"🕒 آخرین بروزرسانی موفق: <b>{esc(s['last'])}</b>\n" f"📊 آخرین نتیجه: <b>{esc(_result_line(s['result']))}</b>\n" f"💱 واحد نرخ: <code>{esc(s['unit'])}</code> | ارز: <code>{esc(s['currency'])}</code>\n" f"⏱ فاصله همگام‌سازی: <code>{esc(s['interval'])}</code> ثانیه")
    await safe_edit(call, text, kb.sintel_admin_menu(s))

@router.callback_query(F.data == "panel_sintel")
async def panel(call: CallbackQuery, state: FSMContext):
    await state.clear(); await call.answer(); await _render(call)

@router.callback_query(F.data == "sintel_set_api")
async def set_api(call: CallbackQuery, state: FSMContext):
    await state.set_state(PanelixAdminStates.api_key); await safe_edit(call, "🔑 <b>کلید API پنلیکس</b>\n\nکلید فعلی: <code>" + esc(mask(await db.get_setting('panelix_api'))) + "</code>\n\nکلید را بفرست؛ پیام آن بلافاصله حذف می‌شود.", kb.cancel_kb("panel_sintel")); await call.answer()

@router.message(PanelixAdminStates.api_key)
async def save_api(message: Message, state: FSMContext):
    key = clean_api_key(message.text or "")
    if not key: await message.answer("❌ کلید خالی است."); return
    try: data = await PanelixClient(key).test_connection()
    except PanelixError as exc: await message.answer("❌ اتصال ناموفق بود.\n" + esc(_humanize_error(exc)), reply_markup=kb.cancel_kb("panel_sintel")); return
    except Exception: log.exception("Panelix key validation failed"); await message.answer("❌ خطای اتصال به پنلیکس.", reply_markup=kb.cancel_kb("panel_sintel")); return
    await db.set_setting("panelix_api", key)
    try: await message.delete()
    except Exception: pass
    await state.clear(); await message.answer(f"✅ کلید ذخیره شد. موجودی پنلیکس: {float(data.get('balance',0)):,.4f} {esc(str(data.get('currency','')))}", reply_markup=kb.sintel_admin_back())

@router.callback_query(F.data == "sintel_test_connection")
async def test_connection(call: CallbackQuery):
    key = await db.get_setting("panelix_api")
    if not key: await call.answer("❌ ابتدا کلید API را تنظیم کنید.", show_alert=True); return
    try:
        data = await PanelixClient(key).test_connection(); await call.answer(f"✅ اتصال موفق: {float(data.get('balance',0)):,.4f} {data.get('currency','')}", show_alert=True)
    except PanelixError as exc: await call.answer(_humanize_error(exc), show_alert=True)

@router.callback_query(F.data.in_({"sintel_sync_catalog", "panelix_sync", "panelix_prices"}))
async def sync(call: CallbackQuery):
    key = await db.get_setting("panelix_api")
    if not key: await call.answer("❌ کلید API تنظیم نشده است.", show_alert=True); return
    await call.answer("⏳ دریافت و بررسی فهرست سرویس‌ها...")
    result = await sync_catalog_from_provider(key)
    if result.get("success"):
        text = "✅ <b>همگام‌سازی پنلیکس انجام شد.</b>\n\n" + f"📦 کل: {result['total']:,}\n➕ جدید: {result['new']:,}\n🔄 تغییرکرده: {result['updated']:,}\n🚫 غیرفعال: {result['unavailable']:,}\n⚠️ خطا: {result['errors']:,}"
    else: text = "❌ <b>همگام‌سازی ناموفق بود</b>\n\n" + esc(str(result.get('error','خطای نامشخص'))) + "\n\nکاتالوگ معتبر قبلی حفظ شد."
    await safe_edit(call, text, kb.sintel_admin_back())

@router.callback_query(F.data == "panelix_status")
async def status(call: CallbackQuery): await call.answer(); await _render(call)

@router.callback_query(F.data.startswith("panelix_set:"))
async def set_setting(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":",1)[1]; labels = {"panelix_rate_unit":"واحد نرخ (per_1000 یا per_order)","panelix_currency":"ارز نرخ (مثلاً USD یا IRR)","panelix_profit_percent":"درصد سود", "panelix_sync_interval":"فاصله بروزرسانی به ثانیه"}
    if key not in labels: await call.answer(); return
    await state.set_state(PanelixAdminStates.setting); await state.update_data(key=key); await safe_edit(call, f"⚙️ <b>{labels[key]}</b>\n\nمقدار جدید را بفرست. برای جلوگیری از قیمت‌گذاری ناامن، تا زمانی که واحد و ارز تأیید نشوند خرید فعال نمی‌شود.", kb.cancel_kb("panel_sintel")); await call.answer()

@router.message(PanelixAdminStates.setting)
async def save_setting(message: Message, state: FSMContext):
    data = await state.get_data(); key = data.get("key"); value = (message.text or "").strip()
    allowed = {"panelix_rate_unit": {"per_1000","per_order"}}
    if key in allowed and value not in allowed[key]: await message.answer("❌ فقط per_1000 یا per_order معتبر است."); return
    if key == "panelix_sync_interval":
        n = parse_number(value)
        if n is None or n < 300: await message.answer("❌ فاصله باید حداقل ۳۰۰ ثانیه باشد."); return
        value = str(int(n))
    if key == "panelix_profit_percent":
        n = parse_number(value)
        if n is None or n < 0: await message.answer("❌ درصد سود نامعتبر است."); return
        value = f"{n:g}"
    await db.set_setting(key, value); await state.clear(); await message.answer("✅ تنظیم ذخیره شد. برای اعمال روی فهرست، همگام‌سازی را اجرا کنید.", reply_markup=kb.sintel_admin_back())
