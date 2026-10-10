"""SimPars - پنل مدیریت حرفه‌ای"""
from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import texts
from config import ADMIN_IDS
from services.fivesim import FiveSimClient, FiveSimError, humanize
from services.payments import get_callback_url
from utils import calc_price, esc, mask, parse_number, safe_edit

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))
log = logging.getLogger(__name__)


class AdminStates(StatesGroup):
    setting = State()
    find_user = State()
    balance = State()
    broadcast = State()


# key: (عنوان, نوع, پنل بازگشت, راهنما)
SETTINGS = {
    "fivesim_api": ("🔑 API Key پنل 5Sim", "secret", "panel_5sim",
                    "کلید API رو از سایت 5sim.net (بخش Profile ← API key) کپی کن و اینجا بفرست."),
    "zibal_merchant": ("💳 کد مرچنت زیبال", "secret", "panel_zibal",
                       "کد مرچنت درگاهت رو از پنل zibal.ir کپی کن و بفرست."),
    "zibal_callback": ("🌐 آدرس بازگشت (Callback URL)", "url", "panel_zibal",
                       "آدرس کامل رو بفرست. مثال:\n<code>http://1.2.3.4:8080/zibal/callback</code>"),
    "rate": ("💱 نرخ تبدیل هر واحد 5Sim به تومان", "float", "panel_price",
             "مثال: اگه هر واحد ۱۲۰۰ تومان باشه بفرست <code>1200</code>"),
    "profit_percent": ("📈 درصد سود", "float", "panel_price", "مثال: <code>30</code>"),
    "min_deposit": ("⬇️ حداقل مبلغ شارژ (تومان)", "int", "panel_price", "مثال: <code>10000</code>"),
    "max_deposit": ("⬆️ حداکثر مبلغ شارژ (تومان)", "int", "panel_price", "مثال: <code>10000000</code>"),
    "referral_percent": ("🎁 درصد پاداش دعوت", "float", "panel_price",
                         "مثال: <code>5</code> (برای غیرفعال کردن <code>0</code>)"),
    "support_text": ("📝 متن بخش پشتیبانی", "text", "admin",
                     "متن جدید رو بفرست (HTML مجازه). برای برگشت به متن پیش‌فرض: <code>-</code>"),
}
TOGGLES = {"force_join": "admin", "maintenance": "admin", "zibal_sandbox": "panel_zibal"}


# ---------------- renderers ----------------
async def _fivesim_balance() -> str:
    token = await db.get_setting("fivesim_api")
    if not token:
        return "—"
    try:
        profile = await FiveSimClient(token).profile()
        return f"{float(profile.get('balance', 0)):,.2f}"
    except FiveSimError as exc:
        return humanize(exc)


async def _status_texts() -> tuple[str, str]:
    fivesim_ok = "✅ متصل" if await db.get_setting("fivesim_api") else "❌ ثبت نشده"
    if await db.get_setting("zibal_sandbox") == "1":
        zibal_ok = "🧪 حالت تست"
    elif await db.get_setting("zibal_merchant"):
        zibal_ok = "✅ فعال"
    else:
        zibal_ok = "❌ ثبت نشده"
    return fivesim_ok, zibal_ok


async def render_admin(call: CallbackQuery) -> None:
    stats = await db.stats()
    fivesim_ok, zibal_ok = await _status_texts()
    text = texts.ADMIN_HOME.format(users=stats["users"], active=stats["active"], fivesim=fivesim_ok, zibal=zibal_ok)
    await safe_edit(call, text, kb.admin_menu(await db.get_setting("force_join"), await db.get_setting("maintenance")))


async def render_5sim(call: CallbackQuery) -> None:
    token = await db.get_setting("fivesim_api")
    balance, status = "—", "❌ ثبت نشده"
    if token:
        try:
            profile = await FiveSimClient(token).profile()
            balance, status = f"{float(profile.get('balance', 0)):,.2f}", "✅ متصل و فعال"
        except FiveSimError as exc:
            status = f"⚠️ {humanize(exc)}"
    await safe_edit(call, texts.ADMIN_5SIM.format(key=esc(mask(token)), status=status, balance=balance),
                    kb.fivesim_admin_kb(bool(token)))


async def render_zibal(call: CallbackQuery) -> None:
    merchant = await db.get_setting("zibal_merchant")
    sandbox = await db.get_setting("zibal_sandbox")
    if sandbox == "1":
        status = "🧪 فعال در حالت تست"
    elif merchant:
        status = "✅ فعال"
    else:
        status = "❌ غیرفعال (مرچنت ثبت نشده)"
    text = texts.ADMIN_ZIBAL.format(
        merchant=esc(mask(merchant)), sandbox=kb.onoff(sandbox),
        callback=esc(await get_callback_url()), status=status,
    )
    await safe_edit(call, text, kb.zibal_admin_kb(sandbox, bool(merchant)))


async def render_price(call: CallbackQuery) -> None:
    rate = await db.get_float("rate", 1000)
    profit = await db.get_float("profit_percent", 30)
    text = texts.ADMIN_PRICE.format(
        rate=rate, profit=f"{profit:g}",
        min=await db.get_int("min_deposit"), max=await db.get_int("max_deposit"),
        ref=f"{await db.get_float('referral_percent'):g}", sample=calc_price(10, rate, profit),
    )
    await safe_edit(call, text, kb.price_admin_kb())


PANELS = {"admin": render_admin, "panel_5sim": render_5sim, "panel_zibal": render_zibal, "panel_price": render_price}


# ---------------- entry ----------------
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    stats = await db.stats()
    fivesim_ok, zibal_ok = await _status_texts()
    await message.answer(
        texts.ADMIN_HOME.format(users=stats["users"], active=stats["active"], fivesim=fivesim_ok, zibal=zibal_ok),
        reply_markup=kb.admin_menu(await db.get_setting("force_join"), await db.get_setting("maintenance")),
    )


@router.callback_query(F.data.in_(set(PANELS)))
async def cb_panel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer()
    await PANELS[call.data](call)


@router.callback_query(F.data == "adm_stats")
async def cb_stats(call: CallbackQuery) -> None:
    await call.answer("⏳ در حال محاسبه...")
    stats = await db.stats()
    await safe_edit(call, texts.ADMIN_STATS.format(fs_balance=await _fivesim_balance(), **stats),
                    kb.markup([[kb.btn("🔄 بروزرسانی", "adm_stats")], [kb.btn("🔙 بازگشت به پنل", "admin")]]))


# ---------------- toggles / delete ----------------
@router.callback_query(F.data.startswith("atog:"))
async def cb_toggle(call: CallbackQuery) -> None:
    key = call.data.split(":", 1)[1]
    if key not in TOGGLES:
        await call.answer()
        return
    new = "0" if await db.get_setting(key) == "1" else "1"
    await db.set_setting(key, new)
    await call.answer("✅ روشن شد" if new == "1" else "❌ خاموش شد")
    await PANELS[TOGGLES[key]](call)


@router.callback_query(F.data.startswith("adel:"))
async def cb_delete(call: CallbackQuery) -> None:
    key = call.data.split(":", 1)[1]
    if key not in SETTINGS:
        await call.answer()
        return
    await db.set_setting(key, "")
    await call.answer("🗑 حذف شد")
    await PANELS[SETTINGS[key][2]](call)


# ---------------- generic settings ----------------
@router.callback_query(F.data.startswith("aset:"))
async def cb_set(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    if key not in SETTINGS:
        await call.answer()
        return
    title, kind, back, hint = SETTINGS[key]
    current = await db.get_setting(key)
    shown = mask(current) if kind == "secret" else (current or "—")
    if kind == "text" and len(shown) > 300:
        shown = shown[:300] + "…"
    await state.set_state(AdminStates.setting)
    await state.update_data(key=key)
    await safe_edit(call, f"{title}\n\n📌 مقدار فعلی: <code>{esc(shown)}</code>\n\n✍️ {hint}", kb.cancel_kb(back))
    await call.answer()


@router.message(AdminStates.setting)
async def msg_set(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    key = data.get("key")
    if key not in SETTINGS:
        await state.clear()
        return
    title, kind, back, _ = SETTINGS[key]
    raw = (message.html_text if kind == "text" else (message.text or "")).strip()
    if not raw:
        await message.answer("❌ مقدار خالیه، دوباره بفرست.", reply_markup=kb.cancel_kb(back))
        return

    extra = ""
    if kind in ("int", "float"):
        number = parse_number(raw)
        if number is None or number < 0 or (key == "rate" and number == 0):
            await message.answer("❌ لطفاً یک عدد معتبر بفرست.", reply_markup=kb.cancel_kb(back))
            return
        value = str(int(number)) if kind == "int" else f"{number:g}"
    elif kind == "url":
        if not raw.startswith(("http://", "https://")):
            await message.answer("❌ آدرس باید با http:// یا https:// شروع بشه.", reply_markup=kb.cancel_kb(back))
            return
        value = raw
    elif kind == "secret":
        value = raw.split()[0]
        try:
            await message.delete()  # حذف پیام حاوی کلید برای امنیت
        except Exception:  # noqa: BLE001
            pass
        if key == "fivesim_api":
            try:
                profile = await FiveSimClient(value).profile()
                extra = f"\n💰 موجودی پنل: <b>{float(profile.get('balance', 0)):,.2f}</b>"
            except FiveSimError as exc:
                await message.answer(f"❌ API نامعتبره یا اتصال برقرار نشد.\n{humanize(exc)}\n\nدوباره بفرست:",
                                     reply_markup=kb.cancel_kb(back))
                return
    else:  # text
        value = "" if raw == "-" else raw

    if key in ("min_deposit", "max_deposit"):
        low = int(value) if key == "min_deposit" else await db.get_int("min_deposit")
        high = int(value) if key == "max_deposit" else await db.get_int("max_deposit")
        if low < 1000 or low > high:
            await message.answer("❌ حداقل باید ≥ ۱,۰۰۰ تومان و کمتر از حداکثر باشه.", reply_markup=kb.cancel_kb(back))
            return

    await db.set_setting(key, value)
    await state.clear()
    await message.answer(f"✅ <b>{title}</b> با موفقیت ذخیره شد.{extra}", reply_markup=kb.admin_back(back))


# ---------------- users ----------------
@router.callback_query(F.data == "adm_user")
async def cb_user_search(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.find_user)
    await safe_edit(call, "👥 <b>مدیریت کاربران</b>\n\n🔎 آیدی عددی یا یوزرنیم کاربر رو بفرست:", kb.cancel_kb("admin"))
    await call.answer()


def _user_card(user, orders: int, spent: int) -> str:
    username = f"@{esc(user['username'])}" if user["username"] else "—"
    return (
        "👤 <b>اطلاعات کاربر</b>\n\n"
        f"🆔 آیدی: <code>{user['user_id']}</code>\n"
        f"👤 نام: <b>{esc(user['full_name'])}</b>\n"
        f"🔗 یوزرنیم: {username}\n"
        f"👛 موجودی: <b>{user['balance']:,} تومان</b>\n"
        f"📦 خرید موفق: <b>{orders}</b>\n"
        f"💸 مجموع خرید: <b>{spent:,} تومان</b>\n"
        f"🚦 وضعیت: {'🚫 مسدود' if user['is_banned'] else '✅ فعال'}"
    )


async def _send_card(target: Message, user_id: int, edit: bool = False) -> None:
    user = await db.get_user(user_id)
    if not user:
        await target.answer("❌ کاربر پیدا نشد.", reply_markup=kb.admin_back())
        return
    orders, spent = await db.user_stats(user_id)
    text, markup = _user_card(user, orders, spent), kb.user_manage_kb(user_id, bool(user["is_banned"]))
    if edit:
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(AdminStates.find_user)
async def msg_find_user(message: Message, state: FSMContext) -> None:
    user = await db.find_user(message.text or "")
    if not user:
        await message.answer("❌ کاربری با این مشخصات پیدا نشد. دوباره بفرست:", reply_markup=kb.cancel_kb("admin"))
        return
    await state.clear()
    await _send_card(message, user["user_id"])


@router.callback_query(F.data.startswith("ubal:"))
async def cb_user_balance(call: CallbackQuery, state: FSMContext) -> None:
    _, uid, op = call.data.split(":")
    await state.set_state(AdminStates.balance)
    await state.update_data(uid=int(uid), op=op)
    label = "➕ افزایش" if op == "add" else "➖ کسر"
    await safe_edit(call, f"{label} موجودی کاربر <code>{uid}</code>\n\n✍️ مبلغ رو به تومان بفرست:", kb.cancel_kb("admin"))
    await call.answer()


@router.message(AdminStates.balance)
async def msg_user_balance(message: Message, state: FSMContext) -> None:
    number = parse_number(message.text or "")
    if number is None or number <= 0:
        await message.answer("❌ مبلغ نامعتبره، دوباره بفرست:", reply_markup=kb.cancel_kb("admin"))
        return
    data = await state.get_data()
    uid, op, amount = data["uid"], data["op"], int(number)
    await state.clear()
    if op == "add":
        await db.add_balance(uid, amount)
        try:
            await message.bot.send_message(uid, f"🎁 <b>{amount:,} تومان</b> توسط مدیریت به کیف پولت اضافه شد 💰")
        except Exception:  # noqa: BLE001
            pass
        await message.answer(f"✅ {amount:,} تومان به موجودی کاربر اضافه شد.")
    else:
        if not await db.deduct_balance(uid, amount):
            await message.answer("❌ موجودی کاربر کمتر از این مبلغه.")
        else:
            await message.answer(f"✅ {amount:,} تومان از موجودی کاربر کسر شد.")
    await _send_card(message, uid)


@router.callback_query(F.data.startswith("uban:"))
async def cb_user_ban(call: CallbackQuery) -> None:
    uid = int(call.data.split(":")[1])
    user = await db.get_user(uid)
    if not user:
        await call.answer("❌ کاربر پیدا نشد.", show_alert=True)
        return
    if uid in ADMIN_IDS:
        await call.answer("⛔️ نمی‌تونی ادمین رو مسدود کنی!", show_alert=True)
        return
    banned = not bool(user["is_banned"])
    await db.set_ban(uid, banned)
    await call.answer("🚫 کاربر مسدود شد" if banned else "✅ کاربر آزاد شد")
    try:
        await call.bot.send_message(uid, texts.BANNED if banned else "✅ <b>دسترسی شما به ربات دوباره فعال شد.</b>")
    except Exception:  # noqa: BLE001
        pass
    await _send_card(call.message, uid, edit=True)


# ---------------- broadcast ----------------
@router.callback_query(F.data == "adm_bc")
async def cb_broadcast(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.broadcast)
    await safe_edit(call, "📢 <b>پیام همگانی</b>\n\n✍️ پیامت رو بفرست (متن، عکس، ویدیو، فایل و ... پشتیبانی میشه):",
                    kb.cancel_kb("admin"))
    await call.answer()


@router.message(AdminStates.broadcast)
async def msg_broadcast(message: Message, state: FSMContext) -> None:
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    count = len(await db.all_user_ids())
    await message.answer(f"👆 پیش‌نمایش پیام بالا\n\n👥 این پیام برای <b>{count:,}</b> کاربر ارسال میشه. تایید می‌کنی؟",
                         reply_markup=kb.broadcast_confirm_kb())


@router.callback_query(F.data == "bc_send")
async def cb_broadcast_send(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    if "message_id" not in data:
        await call.answer("❌ پیامی برای ارسال پیدا نشد.", show_alert=True)
        return
    await call.answer("🚀 ارسال شروع شد")
    await safe_edit(call, "🚀 <b>در حال ارسال پیام همگانی...</b>\n⏳ لطفاً صبر کن.")
    ok = fail = 0
    for uid in await db.all_user_ids():
        for _ in range(2):
            try:
                await call.bot.copy_message(uid, data["chat_id"], data["message_id"])
                ok += 1
                break
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramForbiddenError:
                fail += 1
                break
            except Exception:  # noqa: BLE001
                fail += 1
                break
        await asyncio.sleep(0.05)
    await call.message.answer(f"✅ <b>ارسال همگانی تموم شد</b>\n\n📬 موفق: <b>{ok:,}</b>\n❌ ناموفق: <b>{fail:,}</b>",
                              reply_markup=kb.admin_back())
