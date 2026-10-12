"""SimPars inline keyboards."""
from __future__ import annotations
from urllib.parse import quote
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import texts
from config import CHANNEL_USERNAME, INSTAGRAM_ID, OWNER_USERNAME

def btn(text,cb=None,url=None): return InlineKeyboardButton(text=text,url=url) if url else InlineKeyboardButton(text=text,callback_data=cb or "noop")
def markup(rows): return InlineKeyboardMarkup(inline_keyboard=rows)
def onoff(value): return "✅ روشن" if value=="1" else "❌ خاموش"
CHANNEL_URL="https://t.me/"+CHANNEL_USERNAME.lstrip("@"); OWNER_URL=f"https://t.me/{OWNER_USERNAME}"; INSTAGRAM_URL=f"https://instagram.com/{INSTAGRAM_ID}"
def main_menu(is_admin=False):
    rows=[[btn("🛒 خرید شماره مجازی","buy")],[btn("💰 کیف پول","wallet"),btn("👤 حساب من","account")],[btn("📦 سفارش‌های من","orders"),btn("🎁 دعوت دوستان","referral")],[btn("💬 پشتیبانی","support"),btn("📚 راهنما","help")],[btn("📢 کانال ما",url=CHANNEL_URL),btn("📸 اینستاگرام",url=INSTAGRAM_URL)]]
    if is_admin: rows.append([btn("⚙️ پنل مدیریت","admin")])
    return markup(rows)
def back_main(): return markup([[btn("🏠 بازگشت به منوی اصلی","home")]])
def back_to(cb,text="🔙 بازگشت"): return markup([[btn(text,cb)],[btn("🏠 منوی اصلی","home")]])
def join_kb(): return markup([[btn("📢 عضویت در کانال سیم‌پارس",url=CHANNEL_URL)],[btn("✅ عضو شدم","joined")]])
def services_kb():
    rows=[]; row=[]
    for code,emoji,title in texts.SERVICES:
        row.append(btn(f"{emoji} {title}",f"srv:{code}:0"))
        if len(row)==2: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([btn("🏠 منوی اصلی","home")]); return markup(rows)
def storefront_kb(products):
    return markup([[btn("💎 بهترین قیمت‌ها","cat:cheap"),btn("💰 اقتصادی","cat:economic")],[btn("🌍 همه کشورها و اپراتورها","cat:all")],[btn("🏠 منوی اصلی","home")]])
def product_kb(products,category="all"):
    rows=[]; row=[]
    for product in products:
        known=texts.SERVICE_MAP.get(product); label=f"{known[0]} {known[1]}" if known else f"🌐 {product.replace('_',' ').replace('-',' ').title()}"
        row.append(btn(label,f"srv:{product}:0"))
        if len(row)==2: rows.append(row); row=[]
    if row: rows.append(row)
    rows += [[btn("⬅️ دسته‌بندی خرید","buy")],[btn("🏠 منوی اصلی","home")]]; return markup(rows)
def countries_kb(product,items,page,pages):
    rows=[]; row=[]
    for country,label in items:
        row.append(btn(label,f"cn:{product}:{country}"))
        if len(row)==2: rows.append(row); row=[]
    if row: rows.append(row)
    nav=[]
    if page>0: nav.append(btn("◀️ قبلی",f"srv:{product}:{page-1}"))
    nav.append(btn(f"📄 {page+1}/{pages}","noop"))
    if page<pages-1: nav.append(btn("بعدی ▶️",f"srv:{product}:{page+1}"))
    rows += [nav,[btn("🔄 بروزرسانی قیمت‌ها",f"srv:{product}:{page}")],[btn("🔙 انتخاب سرویس","buy"),btn("🏠 منوی اصلی","home")]]; return markup(rows)
def operators_kb(product,country,items):
    rows=[]
    for operator,price,count in items:
        title="خودکار" if operator in ("auto","any") else operator
        rows.append([btn(f"📡 {title} | 💰 {price:,} تومان | 📦 {count}",f"op:{product}:{country}:{operator}")])
    rows += [[btn("🔙 بازگشت به کشورها",f"srv:{product}:0")],[btn("🏠 منوی اصلی","home")]]; return markup(rows)
def confirm_kb(product,country,operator,enough):
    rows=[[btn("✅ تأیید و خرید",f"ok:{product}:{country}:{operator}")] if enough else [btn("💳 شارژ کیف پول","wallet")]
    rows += [[btn("🔙 انتخاب اپراتور",f"cn:{product}:{country}")],[btn("🏠 منوی اصلی","home")]]; return markup(rows)
def order_kb(order_id): return markup([[btn("🔄 بررسی دریافت کد",f"chk:{order_id}")],[btn("❌ لغو و بازگشت وجه",f"cnl:{order_id}")]])
def order_received_kb(order_id): return markup([[btn("🔄 بررسی پیامک جدید",f"chk:{order_id}")],[btn("✅ اتمام سفارش",f"fin:{order_id}")],[btn("🏠 منوی اصلی","home")]])
def wallet_kb():
    a=[50000,100000,200000,500000]; return markup([[btn(f"💵 {a[0]:,} تومان",f"dep:{a[0]}"),btn(f"💵 {a[1]:,} تومان",f"dep:{a[1]}")],[btn(f"💵 {a[2]:,} تومان",f"dep:{a[2]}"),btn(f"💵 {a[3]:,} تومان",f"dep:{a[3]}")],[btn("✍️ مبلغ دلخواه","dep_custom")],[btn("🏠 منوی اصلی","home")]])
def payment_kb(url,track_id): return markup([[btn("💳 پرداخت آنلاین",url=url)],[btn("✅ پرداخت کردم، بررسی شود",f"vfy:{track_id}")],[btn("🏠 منوی اصلی","home")]])
def cancel_kb(cb="home"): return markup([[btn("❌ انصراف",cb)]])
def support_kb(): return markup([[btn("👨‍💻 ارتباط با پشتیبانی",url=OWNER_URL)],[btn("📢 کانال",url=CHANNEL_URL),btn("📸 اینستاگرام",url=INSTAGRAM_URL)],[btn("🏠 منوی اصلی","home")]])
def referral_kb(link): return markup([[btn("📤 اشتراک‌گذاری لینک",url=f"https://t.me/share/url?url={quote(link)}&text={quote('📱 با سیم‌پارس شماره مجازی بگیر!')}")],[btn("🏠 منوی اصلی","home")]])
def admin_menu(force_join,maintenance): return markup([[btn("📊 آمار و گزارشات","adm_stats")],[btn("🔑 تنظیمات 5Sim","panel_5sim"),btn("💳 درگاه زرین‌پال","panel_zibal")],[btn("💹 قیمت‌گذاری و مالی","panel_price"),btn("👥 مدیریت کاربران","adm_user")],[btn("📢 پیام همگانی","adm_bc"),btn("📝 متن پشتیبانی","aset:support_text")],[btn(f"🔒 جوین اجباری: {onoff(force_join)}","atog:force_join")],[btn(f"🛠 حالت تعمیرات: {onoff(maintenance)}","atog:maintenance")],[btn("🏠 منوی اصلی ربات","home")]])
def admin_back(cb="admin"): return markup([[btn("🔙 بازگشت به پنل",cb)]])
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
def user_manage_kb(uid,banned): return markup([[btn("➕ افزایش موجودی",f"ubal:{uid}:add"),btn("➖ کسر موجودی",f"ubal:{uid}:sub")],[btn("✅ رفع مسدودی" if banned else "🚫 مسدود کردن",f"uban:{uid}"),],[btn("🔍 جستجوی کاربر دیگر","adm_user")],[btn("🔙 بازگشت به پنل","admin")]])
def broadcast_confirm_kb(): return markup([[btn("✅ ارسال برای همه","bc_send")],[btn("❌ انصراف","admin")]])
