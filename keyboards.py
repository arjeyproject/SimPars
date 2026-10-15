"""SimPars inline keyboards."""
from __future__ import annotations
from urllib.parse import quote
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import texts
from config import CHANNEL_USERNAME, INSTAGRAM_ID, OWNER_USERNAME, PREMIUM_EMOJI_DANGER, PREMIUM_EMOJI_PRIMARY, PREMIUM_EMOJI_SUCCESS
CHANNEL_URL = "https://t.me/" + CHANNEL_USERNAME.lstrip("@")
OWNER_URL = f"https://t.me/{OWNER_USERNAME.lstrip('@')}"
INSTAGRAM_URL = f"https://instagram.com/{INSTAGRAM_ID.lstrip('@')}"

def btn(text, callback=None, url=None, *, style=None, icon_custom_emoji_id=None):
    return InlineKeyboardButton(text=text, url=url, callback_data=None if url else (callback or "noop"), style=style, icon_custom_emoji_id=icon_custom_emoji_id)
def markup(rows): return InlineKeyboardMarkup(inline_keyboard=rows)
def onoff(value): return "✅ روشن" if value == "1" else "❌ خاموش"
def main_menu(is_admin=False):
    rows = [[btn("🛒 خرید شماره مجازی", "buy", style="success")], [btn("🔌 خدمات تلگرام و اینستاگرام", "sintel", style="success")], [btn("💰 کیف پول", "wallet", style="primary"), btn("👤 حساب من", "account", style="primary")], [btn("📦 سفارش‌های من", "orders", style="primary"), btn("📦 سفارشات خدمات", "sintel_orders", style="primary")], [btn("🎁 دعوت دوستان", "referral", style="primary"), btn("💬 پشتیبانی", "support", style="primary")], [btn("📚 راهنما", "help", style="primary")], [btn("📢 کانال ما", url=CHANNEL_URL, style="danger"), btn("📸 اینستاگرام", url=INSTAGRAM_URL, style="danger")]]
    if is_admin: rows.append([btn("⚙️ پنل مدیریت", "admin", style="primary")])
    return markup(rows)
def back_main(): return markup([[btn("🏠 بازگشت به منوی اصلی", "home", style="danger")]])
def back_to(callback, text="🔙 بازگشت"): return markup([[btn(text, callback, style="danger")], [btn("🏠 منوی اصلی", "home", style="danger")]])
def cancel_kb(callback="home"): return markup([[btn("انصراف", callback, style="danger")]])
def join_kb(): return markup([[btn("📢 عضویت در کانال سیم‌پارس", url=CHANNEL_URL, style="primary")], [btn("✅ عضو شدم", "joined", style="success")]])
def services_kb(): return product_kb([code for code, _, _ in texts.SERVICES])
def storefront_kb(products=None): return markup([[btn("💎 خرید اقتصادی", "cat:economic:0", style="primary")], [btn("🏠 منوی اصلی", "home", style="danger")]])
def product_kb(products, category="economic", page=0, pages=1):
    rows=[]
    for i in range(0,len(products),3): rows.append([btn(_platform_name(p), f"srv:{p}:0:{category}", style="primary") for p in products[i:i+3]])
    nav=[]
    if page>0: nav.append(btn("⬅️ قبلی", f"cat:{category}:{page-1}", style="primary"))
    nav.append(btn(f"📄 {page+1}/{pages}", "noop", style="success"))
    if page<pages-1: nav.append(btn("بعدی ➡️", f"cat:{category}:{page+1}", style="success"))
    rows += [nav, [btn("🔙 بازگشت", "buy", style="danger")], [btn("🏠 منوی اصلی", "home", style="danger")]]; return markup(rows)
def _platform_name(product):
    emoji,title=texts.SERVICE_MAP.get(product,("🔹",product.replace("_"," ").replace("-"," ")))
    return f"{emoji} {title.title()}"
def countries_kb(product, items, page, pages):
    rows=[[btn(country, cb, style="primary"),btn(price,"noop",style="danger"),btn("🛒 خرید",cb,style="success")] for country,price,cb in items]; nav=[]
    if page>0: nav.append(btn("⬅️ قبلی",f"srv:{product}:{page-1}:economic",style="primary"))
    nav.append(btn(f"📄 {page+1}/{pages}","noop",style="primary"))
    if page<pages-1: nav.append(btn("بعدی ➡️",f"srv:{product}:{page+1}:economic",style="success"))
    rows += [nav,[btn("🔄 بروزرسانی قیمت‌ها",f"srv:{product}:{page}:economic",style="primary")],[btn("🔴 انتخاب پلتفرم","cat:economic:0",style="danger"),btn("🏠 منوی اصلی","home",style="danger")]]; return markup(rows)
def operators_kb(product,country,items,page,pages):
    start=page*12; visible=items[start:start+12]; rows=[]
    for i in range(0,len(visible),4): rows.append([btn(str(start+j+1),f"op:{product}:{country}:{start+j}",style="primary") for j in range(i,min(i+4,len(visible)))])
    nav=[]
    if page>0: nav.append(btn("⬅️ قبلی",f"ops:{product}:{country}:{page-1}",style="primary"))
    nav.append(btn(f"📄 {page+1}/{pages}","noop",style="primary"))
    if page<pages-1: nav.append(btn("بعدی ➡️",f"ops:{product}:{country}:{page+1}",style="success"))
    rows += [nav,[btn("بازگشت به کشورها",f"srv:{product}:0:economic",style="danger")],[btn("🏠 منوی اصلی","home",style="danger")]]; return markup(rows)
def confirm_kb(product,country,operator,enough): return markup([[btn("✅ تأیید و خرید",f"ok:{product}:{country}:{operator}",style="success")] if enough else [btn("💳 شارژ کیف پول","wallet",style="success")],[btn("انتخاب کشور",f"srv:{product}:0:economic",style="primary")],[btn("🏠 منوی اصلی","home",style="danger")]])
def order_kb(order_id): return markup([[btn("🔄 بررسی دریافت کد",f"chk:{order_id}",style="primary")],[btn("❌ لغو و بازگشت وجه",f"cnl:{order_id}",style="danger")]])
def order_received_kb(order_id): return markup([[btn("🔄 بررسی پیامک جدید",f"chk:{order_id}",style="primary")],[btn("✅ اتمام سفارش",f"fin:{order_id}",style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def wallet_kb(): return markup([[btn("💵 50,000 تومان","dep:50000",style="success"),btn("💵 100,000 تومان","dep:100000",style="success")],[btn("💵 200,000 تومان","dep:200000",style="success"),btn("💵 500,000 تومان","dep:500000",style="success")],[btn("✍️ مبلغ دلخواه","dep_custom",style="primary")],[btn("🏠 منوی اصلی","home",style="danger")]])
def payment_kb(url,track_id): return markup([[btn("💳 پرداخت آنلاین",url=url,style="success")],[btn("✅ پرداخت کردم، بررسی شود",f"vfy:{track_id}",style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def support_kb(): return markup([[btn("💬 ارتباط با پشتیبانی",url=OWNER_URL,style="primary")],[btn("📢 کانال",url=CHANNEL_URL,style="success"),btn("📸 اینستاگرام",url=INSTAGRAM_URL,style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def referral_kb(link): return markup([[btn("📤 اشتراک‌گذاری لینک",url=f"https://t.me/share/url?url={quote(link)}&text={quote('با سیم‌پارس شماره مجازی بگیر!')}",style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def admin_menu(force_join,maintenance): return markup([[btn("📊 آمار و گزارشات","adm_stats",style="primary")],[btn("🔑 تنظیمات 5Sim","panel_5sim",style="primary"),btn("💳 درگاه زرین‌پال","panel_zibal",style="primary")],[btn("🔌 پنل خدمات سینتل","panel_sintel",style="success")],[btn("💹 قیمت‌گذاری و مالی","panel_price",style="primary"),btn("👥 مدیریت کاربران","adm_user",style="primary")],[btn("📢 پیام همگانی","adm_bc",style="primary"),btn("📝 متن پشتیبانی","aset:support_text",style="primary")],[btn(f"🔒 جوین اجباری: {onoff(force_join)}","atog:force_join",style="primary")],[btn("📢 کانال قفل اجباری","channel_admin",style="primary")],[btn(f"🛠 حالت تعمیرات: {onoff(maintenance)}","atog:maintenance",style="danger")],[btn("🏠 منوی اصلی ربات","home",style="danger")]])
def admin_back(callback="admin"): return markup([[btn("🔙 بازگشت به پنل",callback,style="danger")]])
def fivesim_admin_kb(has_key): return markup([[btn("✏️ ثبت / تغییر API Key","aset:fivesim_api",style="primary")],[btn("🌐 ورود به سایت 5Sim",url="https://5sim.net",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def zibal_admin_kb(sandbox,has_merchant): return markup([[btn("✏️ ثبت / تغییر Merchant ID","aset:zibal_merchant",style="primary")],[btn(f"🧪 حالت تست: {onoff(sandbox)}","atog:zibal_sandbox",style="primary")],[btn("🌐 ورود به پنل زرین‌پال",url="https://www.zarinpal.com",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def price_admin_kb(): return markup([[btn("💱 نرخ تبدیل","aset:rate",style="primary"),btn("📈 درصد سود","aset:profit_percent",style="primary")],[btn("🛡 نگهبان نرخ دلار","market_admin",style="primary")],[btn("⬇️ حداقل شارژ","aset:min_deposit",style="primary"),btn("⬆️ حداکثر شارژ","aset:max_deposit",style="primary")],[btn("🎁 درصد پاداش دعوت","aset:referral_percent",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def market_admin_kb(has_key,has_url): return markup([[btn("🔐 ثبت / تغییر کلید API","market_set_key",style="primary")],[btn("🌐 ثبت / تغییر آدرس API","market_set_url",style="primary")],[btn("🔄 تست و بروزرسانی نرخ","market_refresh",style="success")],[btn("🔙 بازگشت به قیمت‌گذاری","panel_price",style="danger")]])
def user_manage_kb(uid,banned): return markup([[btn("➕ افزایش موجودی",f"ubal:{uid}:add",style="success"),btn("➖ کسر موجودی",f"ubal:{uid}:sub",style="danger")],[btn("✅ رفع مسدودی" if banned else "🚫 مسدود کردن",f"uban:{uid}",style="danger")],[btn("🔍 جستجوی کاربر دیگر","adm_user",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def broadcast_confirm_kb(): return markup([[btn("✅ ارسال برای همه","bc_send",style="success")],[btn("❌ انصراف","admin",style="danger")]])

def sintel_main_menu(): return markup([[btn("👥 خدمات تلگرام","sintel_telegram",style="success")],[btn("📸 خدمات اینستاگرام","sintel_instagram",style="success")],[btn("📦 سفارشات من","sintel_orders",style="primary")],[btn("🏠 منوی اصلی","home",style="danger")]])
def sintel_platform_menu(platform):
    from services.sintel_catalog import SERVICE_CATEGORIES
    rows=[]
    for key,info in SERVICE_CATEGORIES.get(platform,{}).get("subcategories",{}).items(): rows.append([btn(f"{info['emoji']} {info['title']}",f"stsc:{platform}:{key}",style="primary")])
    rows += [[btn("🔙 بازگشت","sintel",style="danger")],[btn("🏠 منوی اصلی","home",style="danger")]]; return markup(rows)
def sintel_services_list(services):
    rows=[]
    for service in services: rows.append([btn(f"{service.get('name','سرویس')[:38]} | حداقل {service.get('min_quantity',0):,}",f"stlg:{service['service_id']}",style="primary")])
    rows += [[btn("🏠 منوی اصلی","home",style="danger")]]; return markup(rows)
def sintel_confirm_kb(enough): return markup([[btn("✅ ثبت سفارش", "sintel_buy", style="success")] if enough else [btn("💳 شارژ کیف پول", "sintel_wallet", style="success")],[btn("🔙 خدمات سینتل","sintel",style="danger")],[btn("🏠 منوی اصلی","home",style="danger")]])
def sintel_orders_kb(): return markup([[btn("🔌 خرید سرویس جدید","sintel",style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def sintel_order_detail_kb(order_id,status): return markup([[btn("🔄 بروزرسانی وضعیت",f"stch:{order_id}",style="primary")],[btn("🔙 سفارشات سینتل","sintel_orders",style="danger")],[btn("🏠 منوی اصلی","home",style="danger")]])
def sintel_admin_menu(status): return markup([[btn("🔑 تنظیم / تغییر API","sintel_set_api",style="primary")],[btn(f"🔌 فعال/غیرفعال: {'روشن' if status.get('enabled') else 'خاموش'}","sintel_toggle",style="success")],[btn("🔄 تست اتصال","sintel_test_connection",style="primary")],[btn("🔄 همگام‌سازی کاتالوگ","sintel_sync_catalog",style="success")],[btn("📦 مشاهده کاتالوگ","sintel_view_catalog",style="primary")],[btn("📈 تنظیم درصد سود","sintel_set_profit",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def sintel_admin_back(): return markup([[btn("🔙 بازگشت به پنل سینتل","panel_sintel",style="danger")]])
