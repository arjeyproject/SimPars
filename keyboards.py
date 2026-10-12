"""SimPars inline keyboards."""
from __future__ import annotations
from urllib.parse import quote
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import texts
from config import CHANNEL_USERNAME, INSTAGRAM_ID, OWNER_USERNAME

def btn(text: str, cb: str | None = None, url: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url) if url else InlineKeyboardButton(text=text, callback_data=cb or "noop")
def markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup: return InlineKeyboardMarkup(inline_keyboard=rows)
def onoff(value: str) -> str: return "✅ روشن" if value == "1" else "❌ خاموش"
CHANNEL_URL = "https://t.me/" + CHANNEL_USERNAME.lstrip("@"); OWNER_URL = f"https://t.me/{OWNER_USERNAME}"; INSTAGRAM_URL = f"https://instagram.com/{INSTAGRAM_ID}"
def _platform_name(product: str) -> str:
    known = texts.SERVICE_MAP.get(product); title = known[1] if known else product.replace("_", " ").replace("-", " ")
    return " ".join(word[:1].upper() + word[1:].lower() for word in title.split())
def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [[btn("🛒 خرید شماره مجازی", "buy")], [btn("💰 کیف پول", "wallet"), btn("👤 حساب من", "account")], [btn("📦 سفارش‌های من", "orders"), btn("🎁 دعوت دوستان", "referral")], [btn("💬 پشتیبانی", "support"), btn("📚 راهنما", "help")], [btn("📢 کانال ما", url=CHANNEL_URL), btn("📸 اینستاگرام", url=INSTAGRAM_URL)]]
    if is_admin: rows.append([btn("⚙️ پنل مدیریت", "admin")])
    return markup(rows)
def back_main(): return markup([[btn("🏠 بازگشت به منوی اصلی", "home")]])
def back_to(cb: str, text: str = "🔙 بازگشت"): return markup([[btn(text, cb)], [btn("🏠 منوی اصلی", "home")]])
def join_kb(): return markup([[btn("📢 عضویت در کانال سیم‌پارس", url=CHANNEL_URL)], [btn("✅ عضو شدم", "joined")]])
def services_kb(): return product_kb([code for code, _, _ in texts.SERVICES])
def storefront_kb(products): return markup([[btn("بهترین قیمت‌ها", "cat:cheap"), btn("اقتصادی", "cat:economic")], [btn("همه کشورها و اپراتورها", "cat:all")], [btn("🏠 منوی اصلی", "home")]])
def product_kb(products, category="all", page=0, pages=1):
    rows=[]; row=[]
    for product in products:
        row.append(btn(_platform_name(product), f"srv:{product}:0"))
        if len(row)==3: rows.append(row); row=[]
    if row: rows.append(row)
    nav=[]
    if page>0: nav.append(btn("قبلی", f"cat:{category}:{page-1}"))
    nav.append(btn(f"{page+1}/{pages}", "noop"))
    if page<pages-1: nav.append(btn("بعدی", f"cat:{category}:{page+1}"))
    rows += [nav, [btn("دسته‌بندی خرید", "buy")], [btn("🏠 منوی اصلی", "home")]]; return markup(rows)
def countries_kb(product, items, page, pages):
    rows=[[btn(country, buy_cb), btn(price_label, "noop"), btn("خرید", buy_cb)] for country, price_label, buy_cb in items]
    nav=[]
    if page>0: nav.append(btn("قبلی", f"srv:{product}:{page-1}"))
    nav.append(btn(f"{page+1}/{pages}", "noop"))
    if page<pages-1: nav.append(btn("بعدی", f"srv:{product}:{page+1}"))
    rows += [nav, [btn("بروزرسانی قیمت‌ها", f"srv:{product}:{page}")], [btn("انتخاب سرویس", "buy"), btn("🏠 منوی اصلی", "home")]]; return markup(rows)
def operators_kb(product, country, items, page, pages):
    start=page*12; visible=items[start:start+12]; rows=[]; row=[]
    for local_index, _ in enumerate(visible):
        absolute=start+local_index; row.append(btn(str(local_index+1), f"op:{product}:{country}:{absolute}"))
        if len(row)==4: rows.append(row); row=[]
    if row: rows.append(row)
    nav=[]
    if page>0: nav.append(btn("قبلی", f"ops:{product}:{country}:{page-1}"))
    nav.append(btn(f"{page+1}/{pages}", "noop"))
    if page<pages-1: nav.append(btn("بعدی", f"ops:{product}:{country}:{page+1}"))
    rows += [nav, [btn("بازگشت به کشورها", f"srv:{product}:0")], [btn("🏠 منوی اصلی", "home")]]; return markup(rows)
def confirm_kb(product, country, operator, enough):
    rows=[[btn("تأیید و خرید", f"ok:{product}:{country}:{operator}")] if enough else [btn("شارژ کیف پول", "wallet")]]
    rows += [[btn("انتخاب اپراتور", f"cn:{product}:{country}")], [btn("🏠 منوی اصلی", "home")]]; return markup(rows)
def order_kb(order_id): return markup([[btn("بررسی دریافت کد", f"chk:{order_id}")], [btn("لغو و بازگشت وجه", f"cnl:{order_id}")]])
def order_received_kb(order_id): return markup([[btn("بررسی پیامک جدید", f"chk:{order_id}")], [btn("اتمام سفارش", f"fin:{order_id}")], [btn("🏠 منوی اصلی", "home")]])
def wallet_kb():
    amounts=[50_000,100_000,200_000,500_000]; return markup([[btn(f"💵 {amounts[0]:,} تومان",f"dep:{amounts[0]}"),btn(f"💵 {amounts[1]:,} تومان",f"dep:{amounts[1]}")],[btn(f"💵 {amounts[2]:,} تومان",f"dep:{amounts[2]}"),btn(f"💵 {amounts[3]:,} تومان",f"dep:{amounts[3]}")],[btn("✍️ مبلغ دلخواه","dep_custom")],[btn("🏠 منوی اصلی","home")]])
def payment_kb(url,track_id): return markup([[btn("پرداخت آنلاین",url=url)],[btn("پرداخت کردم، بررسی شود",f"vfy:{track_id}")],[btn("🏠 منوی اصلی","home")]])
def cancel_kb(cb="home"): return markup([[btn("انصراف",cb)]])
def support_kb(): return markup([[btn("ارتباط با پشتیبانی",url=OWNER_URL)],[btn("کانال",url=CHANNEL_URL),btn("اینستاگرام",url=INSTAGRAM_URL)],[btn("🏠 منوی اصلی","home")]])
def referral_kb(link): return markup([[btn("اشتراک‌گذاری لینک",url=f"https://t.me/share/url?url={quote(link)}&text={quote('با سیم‌پارس شماره مجازی بگیر!')}")],[btn("🏠 منوی اصلی","home")]])
def admin_menu(force_join,maintenance): return markup([[btn("📊 آمار و گزارشات","adm_stats")],[btn("🔑 تنظیمات 5Sim","panel_5sim"),btn("💳 درگاه زرین‌پال","panel_zibal")],[btn("💹 قیمت‌گذاری و مالی","panel_price"),btn("👥 مدیریت کاربران","adm_user")],[btn("📢 پیام همگانی","adm_bc"),btn("📝 متن پشتیبانی","aset:support_text")],[btn(f"🔒 جوین اجباری: {onoff(force_join)}","atog:force_join")],[btn(f"🛠 حالت تعمیرات: {onoff(maintenance)}","atog:maintenance")],[btn("🏠 منوی اصلی ربات","home")]])
def admin_back(cb="admin"): return markup([[btn("🔙 بازگشت به پنل",cb)])
def fivesim_admin_kb(has_key):
    rows=[[btn("✏️ ثبت / تغییر API Key","aset:fivesim_api")]]
    if has_key: rows.append([btn("🔄 بروزرسانی موجودی","panel_5sim"),btn("🗑 حذف API","adel:fivesim_api")])
    rows += [[btn("🌐 ورود به سایت 5Sim",url="https://5sim.net")],[btn("🔙 بازگشت به پنل","admin")]]; return markup(rows)
def zibal_admin_kb(sandbox,has_merchant):
    rows=[[btn("✏️ ثبت / تغییر Merchant ID","aset:zibal_merchant")],[btn(f"🧪 حالت تست: {onoff(sandbox)}","atog:zibal_sandbox")],[btn("🌐 تنظیم آدرس بازگشت","aset:zibal_callback"),btn("♻️ آدرس پیش‌فرض","adel:zibal_callback")]]
    if has_merchant: rows.append([btn("🗑 حذف Merchant ID","adel:zibal_merchant")])
    rows += [[btn("🌐 ورود به پنل زرین‌پال",url="https://www.zarinpal.com")],[btn("🔙 بازگشت به پنل","admin")]]; return markup(rows)
def price_admin_kb(): return markup([[btn("💱 نرخ تبدیل","aset:rate"),btn("📈 درصد سود","aset:profit_percent")],[btn("🛡 نگهبان نرخ دلار","market_admin")],[btn("⬇️ حداقل شارژ","aset:min_deposit"),btn("⬆️ حداکثر شارژ","aset:max_deposit")],[btn("🎁 درصد پاداش دعوت","aset:referral_percent")],[btn("🔙 بازگشت به پنل","admin")]])
def market_admin_kb(has_key,has_url): return markup([[btn("🔐 ثبت / تغییر کلید API","market_set_key")],[btn("🌐 ثبت / تغییر آدرس API","market_set_url")],[btn("🔄 تست و بروزرسانی نرخ","market_refresh")],[btn("🔙 بازگشت به قیمت‌گذاری","panel_price")]])
def user_manage_kb(uid,banned): return markup([[btn("➕ افزایش موجودی",f"ubal:{uid}:add"),btn("➖ کسر موجودی",f"ubal:{uid}:sub")],[btn("✅ رفع مسدودی" if banned else "🚫 مسدود کردن",f"uban:{uid}")],[btn("🔍 جستجوی کاربر دیگر","adm_user")],[btn("🔙 بازگشت به پنل","admin")]])
def broadcast_confirm_kb(): return markup([[btn("✅ ارسال برای همه","bc_send")],[btn("❌ انصراف","admin")]])
