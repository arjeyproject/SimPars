"""SimPars inline keyboards with Telegram Bot API 9.4 styles."""
from __future__ import annotations
from urllib.parse import quote
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import texts
from config import CHANNEL_USERNAME, INSTAGRAM_ID, OWNER_USERNAME
from config import PREMIUM_EMOJI_SUCCESS, PREMIUM_EMOJI_DANGER, PREMIUM_EMOJI_PRIMARY


def _style(text: str, cb: str | None, url: str | None = None) -> str | None:
    value = f"{text} {cb or ''} {url or ''}".lower()
    if "instagram" in value or "کانال ما" in value or any(x in value for x in ("منوی اصلی", "main", "home", "بازگشت", "انصراف", "لغو", "صفحات")):
        return "danger"
    if "تومان" in value or "قیمت" in value or "1/" in value or "/" in text and text.replace("/", "").replace(" ", "").isdigit():
        return "danger"
    if "بعدی" in value or "next" in value:
        return "success"
    if "خرید" in value or "پرداخت" in value or "اشتراک" in value or "مبلغ دلخواه" in value or "تأیید" in value or "شارژ" in value:
        return "success"
    if "کشور" in value or "انتخاب کشور" in value or "platform" in value or (cb or "").startswith(("srv:", "cat:")) or cb in {"account", "wallet", "referral", "orders"}:
        return "primary"
    if (cb or "").startswith("cn:"):
        return "primary"
    return None


def _emoji_for(style: str | None) -> str | None:
    return {"success": PREMIUM_EMOJI_SUCCESS, "danger": PREMIUM_EMOJI_DANGER, "primary": PREMIUM_EMOJI_PRIMARY}.get(style)


def btn(text: str, cb: str | None = None, url: str | None = None, *, style: str | None = None, icon_custom_emoji_id: str | None = None) -> InlineKeyboardButton:
    style = style or _style(text, cb, url)
    return InlineKeyboardButton(text=text, url=url, callback_data=None if url else (cb or "noop"), style=style, icon_custom_emoji_id=icon_custom_emoji_id or _emoji_for(style))


def markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def onoff(value: str) -> str: return "✅ روشن" if value == "1" else "❌ خاموش"
CHANNEL_URL = "https://t.me/" + CHANNEL_USERNAME.lstrip("@"); OWNER_URL = f"https://t.me/{OWNER_USERNAME}"; INSTAGRAM_URL = f"https://instagram.com/{INSTAGRAM_ID}"


def _platform_name(product: str) -> str:
    known = texts.SERVICE_MAP.get(product); title = known[1] if known else product.replace("_", " ").replace("-", " "); emoji = known[0] if known else "🔹"
    return f"{emoji} " + " ".join(word[:1].upper() + word[1:].lower() for word in title.split())


def main_menu(is_admin=False):
    rows = [[btn("🛒 خرید شماره مجازی", "buy")], [btn("💰 کیف پول", "wallet"), btn("👤 حساب من", "account")], [btn("📦 سفارش‌های من", "orders"), btn("🎁 دعوت دوستان", "referral")], [btn("💬 پشتیبانی", "support"), btn("📚 راهنما", "help")], [btn("📢 کانال ما", url=CHANNEL_URL), btn("📸 اینستاگرام", url=INSTAGRAM_URL)]]
    if is_admin: rows.append([btn("⚙️ پنل مدیریت", "admin")])
    return markup(rows)


def back_main(): return markup([[btn("🏠 بازگشت به منوی اصلی", "home", style="danger")]])
def back_to(cb, text="🔙 بازگشت"): return markup([[btn(text, cb, style="danger")], [btn("🏠 منوی اصلی", "home", style="danger")]])
def join_kb(): return markup([[btn("📢 عضویت در کانال سیم‌پارس", url=CHANNEL_URL)], [btn("✅ عضو شدم", "joined", style="success")]])
def services_kb(): return product_kb([code for code, _, _ in texts.SERVICES])
def storefront_kb(products): return markup([[btn("💎 خرید اقتصادی", "cat:economic:0", style="primary")], [btn("🏠 منوی اصلی", "home", style="danger")]])
def product_kb(products, category="economic", page=0, pages=1):
    rows=[]; row=[]
    for product in products:
        row.append(btn(_platform_name(product), f"srv:{product}:0:economic", style="primary"))
        if len(row)==3: rows.append(row); row=[]
    if row: rows.append(row)
    nav=[]
    if page>0: nav.append(btn("قبلی", f"cat:economic:{page-1}", style="danger"))
    nav.append(btn(f"{page+1}/{pages}", "noop", style="danger"))
    if page<pages-1: nav.append(btn("بعدی", f"cat:economic:{page+1}", style="success"))
    rows += [nav, [btn("🔙 بازگشت", "buy", style="danger")], [btn("🏠 منوی اصلی", "home", style="danger")]]
    return markup(rows)

def countries_kb(product, items, page, pages):
    rows = [[btn(country, buy_cb, style="primary"), btn(price_label, "noop", style="danger"), btn("🛒 خرید", buy_cb, style="success")] for country, price_label, buy_cb in items]
    nav=[]
    if page>0: nav.append(btn("قبلی", f"srv:{product}:{page-1}:economic", style="danger"))
    nav.append(btn(f"{page+1}/{pages}", "noop", style="danger"))
    if page<pages-1: nav.append(btn("بعدی", f"srv:{product}:{page+1}:economic", style="success"))
    rows += [nav, [btn("🔄 بروزرسانی قیمت‌ها", f"srv:{product}:{page}:economic", style="primary")], [btn("انتخاب پلتفرم", "cat:economic:0", style="primary"), btn("🏠 منوی اصلی", "home", style="danger")]]
    return markup(rows)

def operators_kb(product,country,items,page,pages):
    start=page*12; visible=items[start:start+12]; rows=[]; row=[]
    for local_index,_ in enumerate(visible):
        absolute=start+local_index; row.append(btn(str(local_index+1),f"op:{product}:{country}:{absolute}", style="primary"))
        if len(row)==4: rows.append(row); row=[]
    if row: rows.append(row)
    nav=[]
    if page>0: nav.append(btn("قبلی",f"ops:{product}:{country}:{page-1}", style="danger"))
    nav.append(btn(f"{page+1}/{pages}","noop", style="danger"))
    if page<pages-1: nav.append(btn("بعدی",f"ops:{product}:{country}:{page+1}", style="success"))
    rows += [nav, [btn("بازگشت به کشورها",f"srv:{product}:0:economic", style="danger")], [btn("🏠 منوی اصلی","home", style="danger")]]
    return markup(rows)

def confirm_kb(product,country,operator,enough):
    rows = [[btn("✅ تأیید و خرید", f"ok:{product}:{country}:{operator}", style="success")]] if enough else [[btn("💳 شارژ کیف پول", "wallet", style="success")]]
    rows += [[btn("انتخاب کشور", f"srv:{product}:0:economic", style="primary")], [btn("🏠 منوی اصلی", "home", style="danger")]]
    return markup(rows)

def order_kb(order_id): return markup([[btn("🔄 بررسی دریافت کد", f"chk:{order_id}", style="primary")], [btn("❌ لغو و بازگشت وجه", f"cnl:{order_id}", style="danger")]])
def order_received_kb(order_id): return markup([[btn("🔄 بررسی پیامک جدید", f"chk:{order_id}", style="primary")], [btn("✅ اتمام سفارش", f"fin:{order_id}", style="success")], [btn("🏠 منوی اصلی", "home", style="danger")]])
def wallet_kb():
    amounts=[50000,100000,200000,500000]
    return markup([[btn(f"💵 {amounts[0]:,} تومان",f"dep:{amounts[0]}",style="success"),btn(f"💵 {amounts[1]:,} تومان",f"dep:{amounts[1]}",style="success")],[btn(f"💵 {amounts[2]:,} تومان",f"dep:{amounts[2]}",style="success"),btn(f"💵 {amounts[3]:,} تومان",f"dep:{amounts[3]}",style="success")],[btn("✍️ مبلغ دلخواه","dep_custom",style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def payment_kb(url,track_id): return markup([[btn("💳 پرداخت آنلاین",url=url,style="success")],[btn("✅ پرداخت کردم، بررسی شود",f"vfy:{track_id}",style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def cancel_kb(cb="home"): return markup([[btn("انصراف",cb,style="danger")]])
def support_kb(): return markup([[btn("ارتباط با پشتیبانی",url=OWNER_URL,style="primary")],[btn("کانال",url=CHANNEL_URL,style="danger"),btn("اینستاگرام",url=INSTAGRAM_URL,style="danger")],[btn("🏠 منوی اصلی","home",style="danger")]])
def referral_kb(link): return markup([[btn("اشتراک‌گذاری لینک",url=f"https://t.me/share/url?url={quote(link)}&text={quote('با سیم‌پارس شماره مجازی بگیر!')}",style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def admin_menu(force_join,maintenance): return markup([[btn("📊 آمار و گزارشات","adm_stats",style="primary")],[btn("🔑 تنظیمات 5Sim","panel_5sim",style="primary"),btn("💳 درگاه زرین‌پال","panel_zibal",style="primary")],[btn("💹 قیمت‌گذاری و مالی","panel_price",style="primary"),btn("👥 مدیریت کاربران","adm_user",style="primary")],[btn("📢 پیام همگانی","adm_bc",style="primary"),btn("📝 متن پشتیبانی","aset:support_text",style="primary")],[btn(f"🔒 جوین اجباری: {onoff(force_join)}","atog:force_join",style="primary")],[btn(f"🛠 حالت تعمیرات: {onoff(maintenance)}","atog:maintenance",style="danger")],[btn("🏠 منوی اصلی ربات","home",style="danger")]])
def admin_back(cb="admin"): return markup([[btn("🔙 بازگشت به پنل",cb,style="danger")]])
def fivesim_admin_kb(has_key): return markup([[btn("✏️ ثبت / تغییر API Key","aset:fivesim_api",style="primary")],[btn("🌐 ورود به سایت 5Sim",url="https://5sim.net",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def zibal_admin_kb(sandbox,has_merchant): return markup([[btn("✏️ ثبت / تغییر Merchant ID","aset:zibal_merchant",style="primary")],[btn(f"🧪 حالت تست: {onoff(sandbox)}","atog:zibal_sandbox",style="primary")],[btn("🌐 ورود به پنل زرین‌پال",url="https://www.zarinpal.com",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def price_admin_kb(): return markup([[btn("💱 نرخ تبدیل","aset:rate",style="primary"),btn("📈 درصد سود","aset:profit_percent",style="primary")],[btn("🛡 نگهبان نرخ دلار","market_admin",style="primary")],[btn("⬇️ حداقل شارژ","aset:min_deposit",style="primary"),btn("⬆️ حداکثر شارژ","aset:max_deposit",style="primary")],[btn("🎁 درصد پاداش دعوت","aset:referral_percent",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def market_admin_kb(has_key,has_url): return markup([[btn("🔐 ثبت / تغییر کلید API","market_set_key",style="primary")],[btn("🌐 ثبت / تغییر آدرس API","market_set_url",style="primary")],[btn("🔄 تست و بروزرسانی نرخ","market_refresh",style="success")],[btn("🔙 بازگشت به قیمت‌گذاری","panel_price",style="danger")]])
def user_manage_kb(uid,banned): return markup([[btn("➕ افزایش موجودی",f"ubal:{uid}:add",style="success"),btn("➖ کسر موجودی",f"ubal:{uid}:sub",style="danger")],[btn("✅ رفع مسدودی" if banned else "🚫 مسدود کردن",f"uban:{uid}",style="danger")],[btn("🔍 جستجوی کاربر دیگر","adm_user",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def broadcast_confirm_kb(): return markup([[btn("✅ ارسال برای همه","bc_send",style="success")],[btn("❌ انصراف","admin",style="danger")]])
