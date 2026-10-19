"""Inline keyboards with consistent Persian navigation."""
from __future__ import annotations
from urllib.parse import quote
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import texts
from config import CHANNEL_USERNAME, INSTAGRAM_ID, OWNER_USERNAME
CHANNEL_URL="https://t.me/"+CHANNEL_USERNAME.lstrip("@"); OWNER_URL=f"https://t.me/{OWNER_USERNAME.lstrip('@')}"; INSTAGRAM_URL=f"https://instagram.com/{INSTAGRAM_ID.lstrip('@')}"
def btn(text,callback=None,url=None,*,style=None,icon_custom_emoji_id=None): return InlineKeyboardButton(text=text,url=url,callback_data=None if url else (callback or "noop"),style=style,icon_custom_emoji_id=icon_custom_emoji_id)
def markup(rows): return InlineKeyboardMarkup(inline_keyboard=rows)
def onoff(value): return "✅ روشن" if value=="1" else "❌ خاموش"
def _social_back(callback="sintel"): return [btn("🔙 بازگشت",callback,style="primary"),btn("🏠 منوی اصلی","home",style="primary")]
def main_menu(is_admin=False):
    rows=[[btn("📱 خرید شماره مجازی","buy",style="success")],[btn("📣 خدمات شبکه‌های اجتماعی","sintel",style="success")],[btn("💰 کیف پول","wallet",style="primary"),btn("👤 حساب من","account",style="primary")],[btn("📦 سفارش‌های من","orders",style="primary"),btn("📦 سفارشات خدمات","sintel_orders",style="primary")],[btn("🎁 دعوت دوستان","referral",style="primary"),btn("💬 پشتیبانی","support",style="primary")],[btn("📚 راهنما","help",style="primary")],[btn("📢 کانال ما",url=CHANNEL_URL,style="danger"),btn("📸 اینستاگرام",url=INSTAGRAM_URL,style="danger")]]
    if is_admin: rows.append([btn("⚙️ پنل مدیریت","admin",style="primary")])
    return markup(rows)
def back_main(): return markup([[btn("🏠 بازگشت به منوی اصلی","home",style="danger")]])
def back_to(c,text="🔙 بازگشت"): return markup([[btn(text,c,style="primary")],[btn("🏠 منوی اصلی","home",style="primary")]])
def cancel_kb(c="home"): return markup([[btn("انصراف",c,style="primary")]])
def join_kb(): return markup([[btn("📢 عضویت در کانال سیم‌پارس",url=CHANNEL_URL,style="primary")],[btn("✅ عضو شدم","joined",style="success")]])
def services_kb(): return product_kb([x[0] for x in texts.SERVICES])
def storefront_kb(products=None): return markup([[btn("💎 خرید اقتصادی","cat:economic:0",style="primary")],[btn("🏠 منوی اصلی","home",style="primary")]])
def _platform_name(p):
    e,t=texts.SERVICE_MAP.get(p,("🔹",p.replace("_"," ").replace("-"," "))); return f"{e} {t}"
def product_kb(products,category="economic",page=0,pages=1):
    rows=[]
    for i in range(0,len(products),2): rows.append([btn(_platform_name(p),f"srv:{p}:0:{category}",style=("danger" if i//2%2==0 else "success")) for p in products[i:i+2]])
    nav=[]
    if page>0: nav.append(btn("⬅️ صفحه قبل",f"cat:{category}:{page-1}",style="primary"))
    nav.append(btn(f"📄 {page+1}/{pages}","noop",style="primary"))
    if page<pages-1: nav.append(btn("صفحه بعد ➡️",f"cat:{category}:{page+1}",style="primary"))
    return markup(rows+[nav,_social_back("buy")])
def countries_kb(product,items,page=0,pages=1):
    rows=[]
    for i in range(0,len(items),2): rows.append([btn(f"{a}\n{c}",b,style=("danger" if i//2%2==0 else "success")) for a,c,b in items[i:i+2]])
    nav=[]
    if page>0: nav.append(btn("⬅️ صفحه قبل",f"srv:{product}:{page-1}",style="primary"))
    if page<pages-1: nav.append(btn("صفحه بعد ➡️",f"srv:{product}:{page+1}",style="primary"))
    return markup(rows+([nav] if nav else [])+[_social_back("buy")])
def operators_kb(product,country,items,page,pages): return markup([[btn(str(page*12+i+1),f"op:{product}:{country}:{page*12+i}",style=("danger" if i//2%2==0 else "success")) for i in range(min(4,len(items)))],_social_back("buy")])
def confirm_kb(product,country,operator,enough):
    rows=[[btn("✅ تأیید و خرید",f"ok:{product}:{country}:{operator}",style="success")]]
    if not enough: rows.append([btn("💳 شارژ کیف پول","wallet",style="success")])
    return markup(rows+[[btn("🏠 منوی اصلی","home",style="primary")]])
def order_kb(i): return markup([[btn("🔄 بررسی وضعیت",f"stch:{i}",style="primary")],[btn("❌ لغو و بررسی بازگشت وجه",f"cnl:{i}",style="danger")]])
def order_received_kb(i): return order_kb(i)
def wallet_kb(): return markup([[btn("💵 ۵۰٬۰۰۰ تومان","dep:50000",style="success"),btn("💵 ۱۰۰٬۰۰۰ تومان","dep:100000",style="success")],[btn("💵 ۲۰۰٬۰۰۰ تومان","dep:200000",style="success"),btn("💵 ۵۰۰٬۰۰۰ تومان","dep:500000",style="success")],[btn("✍️ مبلغ دلخواه","dep_custom",style="primary")],[btn("🏠 منوی اصلی","home",style="primary")]])
def payment_kb(url,i): return markup([[btn("💳 پرداخت آنلاین",url=url,style="success")],[btn("✅ پرداخت کردم، بررسی شود",f"vfy:{i}",style="success")],[btn("🏠 منوی اصلی","home",style="primary")]])
def support_kb(): return markup([[btn("💬 ارتباط با پشتیبانی",url=OWNER_URL,style="primary")],[btn("📢 کانال",url=CHANNEL_URL,style="success"),btn("📸 اینستاگرام",url=INSTAGRAM_URL,style="success")],[btn("🏠 منوی اصلی","home",style="primary")]])
def referral_kb(link): return markup([[btn("📤 اشتراک‌گذاری لینک",url=f"https://t.me/share/url?url={quote(link)}&text={quote('با سیم‌پارس شماره مجازی بگیر!')}",style="success")],[btn("🏠 منوی اصلی","home",style="primary")]])
def admin_menu(f,m): return markup([[btn("📊 آمار و گزارشات","adm_stats",style="primary")],[btn("⚙️ مدیریت پنلیکس","panel_sintel",style="success")],[btn("🔑 تنظیمات شماره مجازی","panel_5sim",style="primary"),btn("💳 درگاه زرین‌پال","panel_zibal",style="primary")],[btn("💹 قیمت‌گذاری و مالی","panel_price",style="primary"),btn("👥 مدیریت کاربران","adm_user",style="primary")],[btn("📢 پیام همگانی","adm_bc",style="primary"),btn("📝 متن پشتیبانی","aset:support_text",style="primary")],[btn(f"🔒 جوین اجباری: {onoff(f)}","atog:force_join",style="primary")],[btn("📢 کانال قفل اجباری","channel_admin",style="primary")],[btn(f"🛠 حالت تعمیرات: {onoff(m)}","atog:maintenance",style="danger")],[btn("🏠 منوی اصلی ربات","home",style="primary")]])
def admin_back(c="admin"): return markup([[btn("🔙 بازگشت به پنل",c,style="primary")]])
def fivesim_admin_kb(has): return markup([[btn("✏️ ثبت / تغییر کلید API","aset:fivesim_api",style="primary")],[btn("🌐 ورود به سایت شماره مجازی",url="https://5sim.net",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="primary")]])
def zibal_admin_kb(sandbox,has): return markup([[btn("✏️ ثبت / تغییر مرچنت","aset:zibal_merchant",style="primary")],[btn(f"🧪 حالت تست: {onoff(sandbox)}","atog:zibal_sandbox",style="primary")],[btn("🌐 ورود به پنل زرین‌پال",url="https://www.zarinpal.com",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="primary")]])
def price_admin_kb(): return markup([[btn("💱 نرخ تبدیل","aset:rate",style="primary"),btn("📈 درصد سود","aset:profit_percent",style="primary")],[btn("🛡 نگهبان نرخ دلار","market_admin",style="primary")],[btn("⬇️ حداقل شارژ","aset:min_deposit",style="primary"),btn("⬆️ حداکثر شارژ","aset:max_deposit",style="primary")],[btn("🎁 درصد پاداش دعوت","aset:referral_percent",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="primary")]])
def market_admin_kb(a,b): return admin_back("panel_price")
def user_manage_kb(uid,banned): return markup([[btn("➕ افزایش موجودی",f"ubal:{uid}:add",style="success"),btn("➖ کسر موجودی",f"ubal:{uid}:sub",style="danger")],[btn("✅ رفع مسدودی" if banned else "🚫 مسدود کردن",f"uban:{uid}",style="danger")],[btn("🔍 جستجوی کاربر دیگر","adm_user",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="primary")]])
def broadcast_confirm_kb(): return markup([[btn("✅ ارسال برای همه","bc_send",style="success")],[btn("❌ انصراف","admin",style="danger")]])
def sintel_main_menu(): return markup([[btn("🛒 انتخاب خدمات","sintel_telegram",style="success")],[btn("📦 سفارشات من","sintel_orders",style="primary")],[btn("🏠 منوی اصلی","home",style="primary")]])
def sintel_platform_menu(p):
    from services.sintel_catalog import PLATFORM_LABELS
    e,t=PLATFORM_LABELS.get(p,("📱",p)); return markup([[btn(f"{e} {t}",f"stsc:{p}:all",style="danger")],_social_back("sintel")])
def sintel_services_list(ss):
    items=[(f"{s.get('display_name') or s.get('name','سرویس')[:34]} | حداقل {s.get('min_quantity',0):,}",f"stlg:{s['service_id']}") for s in ss]; rows=[]
    for i in range(0,len(items),2): rows.append([btn(label,callback,style=("danger" if i//2%2==0 else "success")) for label,callback in items[i:i+2]])
    return markup(rows+[_social_back("sintel")])
def sintel_confirm_kb(ok):
    rows=[[btn("✅ تأیید سفارش","sintel_buy",style="success")] if ok else [btn("💳 شارژ کیف پول","sintel_wallet",style="success")]]
    rows.append(_social_back("sintel"))
    return markup(rows)
def sintel_orders_kb(): return markup([[btn("🛒 خرید سرویس جدید","sintel",style="success")],[btn("🏠 منوی اصلی","home",style="primary")]])
def sintel_order_detail_kb(i,s): return markup([[btn("🔄 بروزرسانی وضعیت",f"stch:{i}",style="primary")],_social_back("sintel_orders")])
def sintel_admin_menu(s): return markup([[btn("🔑 تنظیم کلید API","sintel_set_api",style="primary")],[btn("🔌 بررسی اتصال پنلیکس","sintel_test_connection",style="primary")],[btn("📥 دریافت آخرین سرویس‌ها","sintel_sync_catalog",style="success")],[btn("🔄 بروزرسانی قیمت‌ها","panelix_prices",style="success")],[btn("📊 وضعیت همگام‌سازی","panelix_status",style="primary")],[btn("💰 تنظیم سود و قیمت فروش","panelix_set:panelix_profit_percent",style="primary")],[btn("💱 تنظیم واحد نرخ","panelix_set:panelix_rate_unit",style="primary"),btn("💵 تنظیم ارز","panelix_set:panelix_currency",style="primary")],[btn("⏱ تنظیم فاصله بروزرسانی","panelix_set:panelix_sync_interval",style="primary")],[btn("📋 گزارش خطاها","panelix_status",style="primary")],[btn("🔙 بازگشت به مدیریت پنلیکس","admin",style="primary")]])
def sintel_catalog_menu(): return markup([[btn("📦 کاتالوگ خدمات","sintel_telegram",style="primary")],[btn("🔙 بازگشت به مدیریت پنلیکس","panel_sintel",style="primary")]])
def sintel_admin_back(): return markup([[btn("🔙 بازگشت به مدیریت پنلیکس","panel_sintel",style="primary")]])
