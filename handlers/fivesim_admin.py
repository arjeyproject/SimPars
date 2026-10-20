"""پنل 5Sim: بروزرسانی واقعی قیمت‌ها + تنظیمات بروزرسانی خودکار."""
from __future__ import annotations
import logging, time
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
import database as db
import keyboards as kb
import texts
from config import ADMIN_IDS
from handlers import admin
from services.fivesim import FiveSimClient, FiveSimError, humanize, refresh_all
from utils import esc, mask, safe_edit

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))
log = logging.getLogger(__name__)
DEFAULT_MINUTES = 5


async def auto_enabled() -> bool:
    return await db.get_setting("fivesim_auto_refresh") != "0"


async def refresh_minutes() -> int:
    return max(1, await db.get_int("fivesim_refresh_minutes", DEFAULT_MINUTES))


async def run_refresh() -> dict:
    info = await refresh_all()
    await db.set_setting("fivesim_last_refresh", str(int(info["time"])))
    await db.set_setting("fivesim_last_refresh_summary", f"{info['products']}|{info['countries']}")
    return info


def _ago(ts: int) -> str:
    if ts <= 0:
        return "هنوز انجام نشده"
    d = max(0, int(time.time()) - ts)
    if d < 60:
        return "همین الان"
    if d < 3600:
        return f"{d // 60} دقیقه پیش"
    if d < 86400:
        return f"{d // 3600} ساعت پیش"
    return f"{d // 86400} روز پیش"


def fivesim_kb(auto: bool, minutes: int):
    return kb.markup([
        [kb.btn("🔄 بروزرسانی اطلاعات 5Sim", "fs_refresh", style="success")],
        [kb.btn(f"♻️ بروزرسانی خودکار: {kb.onoff('1' if auto else '0')}", "fs_auto", style="primary"),
         kb.btn(f"⏱ هر {minutes} دقیقه", "aset:fivesim_refresh_minutes", style="primary")],
        [kb.btn("✏️ ثبت / تغییر کلید API", "aset:fivesim_api", style="primary")],
        [kb.btn("🌐 ورود به سایت شماره مجازی", url="https://5sim.net", style="primary")],
        [kb.btn("🔙 بازگشت به پنل", "admin", style="primary")],
    ])


async def render_5sim(call: CallbackQuery, note: str = "") -> None:
    token = await db.get_setting("fivesim_api")
    balance, status = "—", "❌ ثبت نشده"
    if token:
        try:
            profile = await FiveSimClient(token).profile()
            balance, status = f"{float(profile.get('balance', 0)):,.2f}", "✅ متصل و فعال"
        except FiveSimError as exc:
            status = f"⚠️ {humanize(exc)}"
    auto, minutes = await auto_enabled(), await refresh_minutes()
    summary = (await db.get_setting("fivesim_last_refresh_summary")).split("|")
    text = texts.ADMIN_5SIM.format(key=esc(mask(token)), status=status, balance=balance)
    text += (f"\n\n♻️ بروزرسانی خودکار: {kb.onoff('1' if auto else '0')} (هر {minutes} دقیقه)"
             f"\n🕒 آخرین بروزرسانی قیمت‌ها: {_ago(await db.get_int('fivesim_last_refresh', 0))}")
    if len(summary) == 2 and summary[0]:
        text += f"\n📦 {summary[0]} سرویس در {summary[1]} کشور"
    text += "\n🏷 انتخاب اپراتور: بهترین کیفیت، سپس گران‌ترین"
    if note:
        text += f"\n\n{note}"
    await safe_edit(call, text, fivesim_kb(auto, minutes))


# جایگزینی پنل قدیمی و افزودن تنظیم فاصله بروزرسانی
admin.PANELS["panel_5sim"] = render_5sim
admin.SETTINGS["fivesim_refresh_minutes"] = ("⏱ فاصله بروزرسانی خودکار 5Sim (دقیقه)", "int", "panel_5sim",
                                             "یک عدد به دقیقه بفرست. مثال: <code>5</code> (حداقل ۱)")


@router.callback_query(F.data == "fs_refresh")
async def cb_refresh(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer("⏳ در حال دریافت قیمت‌ها از 5Sim...")
    try:
        info = await run_refresh()
        note = f"✅ بروزرسانی انجام شد: {info['products']} سرویس، {info['countries']} کشور."
    except FiveSimError as exc:
        note = f"⚠️ بروزرسانی ناموفق بود: {humanize(exc)}"
    except Exception:  # noqa: BLE001
        log.exception("5Sim manual refresh failed")
        note = "⚠️ بروزرسانی ناموفق بود."
    await render_5sim(call, note)


@router.callback_query(F.data == "fs_auto")
async def cb_auto(call: CallbackQuery) -> None:
    new = "1" if await db.get_setting("fivesim_auto_refresh") == "0" else "0"
    await db.set_setting("fivesim_auto_refresh", new)
    await call.answer("✅ بروزرسانی خودکار روشن شد" if new == "1" else "❌ بروزرسانی خودکار خاموش شد")
    await render_5sim(call)
