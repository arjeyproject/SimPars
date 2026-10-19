"""SimPars inline keyboards."""
from __future__ import annotations
from urllib.parse import quote
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import texts
from config import CHANNEL_USERNAME, INSTAGRAM_ID, OWNER_USERNAME
CHANNEL_URL="https://t.me/"+CHANNEL_USERNAME.lstrip("@"); OWNER_URL=f"https://t.me/{OWNER_USERNAME.lstrip('@')}"; INSTAGRAM_URL=f"https://instagram.com/{INSTAGRAM_ID.lstrip('@')}"
def btn(text,callback=None,url=None,*,style=None,icon_custom_emoji_id=None): return InlineKeyboardButton(text=text,url=url,callback_data=None if url else (callback or "noop"),style=style,icon_custom_emoji_id=icon_custom_emoji_id)
def markup(rows): return InlineKeyboardMarkup(inline_keyboard=rows)
def onoff(value): return "✅ روشن" if value=="1" else "❌ خاموش"
def main_menu(is_admin=False):
    rows=[[btn("📱 خرید شماره مجازی","buy",style="success")],[btn("✈️ خدمات تلگرام","sintel_telegram",style="success"),btn("📸 خدمات اینستاگرام","sintel_instagram",style="success")],[btn("💰 کیف پول","wallet",style="primary"),btn("👤 حساب من","account",style="primary")],[btn("📦 سفارش‌های من","orders",style="primary"),btn("📦 سفارشات خدمات","sintel_orders",style="primary")],[btn("🎁 دعوت دوستان","referral",style="primary"),btn("💬 پشتیبانی","support",style="primary")],[btn("📚 راهنما","help",style="primary")],[btn("📢 کانال ما",url=CHANNEL_URL,style="danger"),btn("📸 اینستاگرام",url=INSTAGRAM_URL,style="danger")]]
    if is_admin: rows.append([btn("⚙️ پنل مدیریت","admin",style="primary")])
    return markup(rows)
def back_main(): return markup([[btn("🏠 بازگشت به منوی اصلی","home",style="danger")]])
def back_to(c,text="🔙 بازگشت"): return markup([[btn(text,c,style="danger")],[btn("🏠 منوی اصلی","home",style="danger")]])
def cancel_kb(c="home"): return markup([[btn("انصراف",c,style="danger")]])
def join_kb(): return markup([[btn("📢 عضویت در کانال سیم‌پارس",url=CHANNEL_URL,style="primary")],[btn("✅ عضو شدم","joined",style="success")]])
def services_kb(): return product_kb([x[0] for x in texts.SERVICES])
def storefront_kb(products=None): return markup([[btn("💎 خرید اقتصادی","cat:economic:0",style="primary")],[btn("🏠 منوی اصلی","home",style="danger")]])
def _platform_name(p):
    e,t=texts.SERVICE_MAP.get(p,("🔹",p.replace("_"," ").replace("-"," "))); return f"{e} {t.title()}"
def product_kb(products,category="economic",page=0,pages=1):
    rows=[[btn(_platform_name(p),f"srv:{p}:0:{category}",style="primary") for p in products[i:i+3]] for i in range(0,len(products),3)]; nav=[]
    if page>0: nav.append(btn("⬅️ قبلی",f"cat:{category}:{page-1}",style="primary"))
    nav.append(btn(f"📄 {page+1}/{pages}","noop",style="success"))
    if page<pages-1: nav.append(btn("بعدی ➡️",f"cat:{category}:{page+1}",style="success"))
    return markup(rows+[nav,[btn("🔙 بازگشت","buy",style="danger")],[btn("🏠 منوی اصلی","home",style="danger")]])
def countries_kb(product,items,page,pages): return markup([[btn(a,b,style="primary"),btn(c,"noop",style="danger"),btn("🛒 خرید",b,style="success")] for a,c,b in items]+[[btn("🏠 منوی اصلی","home",style="danger")]])
def operators_kb(product,country,items,page,pages): return markup([[btn(str(page*12+i+1),f"op:{product}:{country}:{page*12+i}",style="primary") for i in range(min(4,len(items)))],[btn("🏠 منوی اصلی","home",style="danger")]])
def confirm_kb(product,country,operator,enough): return markup([[btn("✅ تأیید و خرید",f"ok:{product}:{country}:{operator}",style="success")],[btn("💳 شارژ کیف پول","wallet",style="success")] if not enough else [[btn("✅ تأیید و خرید",f"ok:{product}:{country}:{operator}",style="success")]] + [[btn("🏠 منوی اصلی","home",style="danger")]])
def order_kb(i): return markup([[btn("🔄 بررسی دریافت کد",f"chk:{i}",style="primary")],[btn("❌ لغو و بازگشت وجه",f"cnl:{i}",style="danger")]])
def order_received_kb(i): return order_kb(i)
def wallet_kb(): return markup([[btn("💵 50,000 تومان","dep:50000",style="success"),btn("💵 100,000 تومان","dep:100000",style="success")],[btn("💵 200,000 تومان","dep:200000",style="success"),btn("💵 500,000 تومان","dep:500000",style="success")],[btn("✍️ مبلغ دلخواه","dep_custom",style="primary")],[btn("🏠 منوی اصلی","home",style="danger")]])
def payment_kb(url,i): return markup([[btn("💳 پرداخت آنلاین",url=url,style="success")],[btn("✅ پرداخت کردم، بررسی شود",f"vfy:{i}",style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def support_kb(): return markup([[btn("💬 ارتباط با پشتیبانی",url=OWNER_URL,style="primary")],[btn("📢 کانال",url=CHANNEL_URL,style="success"),btn("📸 اینستاگرام",url=INSTAGRAM_URL,style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def referral_kb(link): return markup([[btn("📤 اشتراک‌گذاری لینک",url=f"https://t.me/share/url?url={quote(link)}&text={quote('با سیم‌پارس شماره مجازی بگیر!')}",style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def admin_menu(f,m): return markup([[btn("📊 آمار و گزارشات","adm_stats",style="primary")],[btn("🔑 تنظیمات 5Sim","panel_5sim",style="primary"),btn("💳 درگاه زرین‌پال","panel_zibal",style="primary")],[btn("🔌 پنل خدمات سینتل","panel_sintel",style="success")],[btn("💹 قیمت‌گذاری و مالی","panel_price",style="primary"),btn("👥 مدیریت کاربران","adm_user",style="primary")],[btn("📢 پیام همگانی","adm_bc",style="primary"),btn("📝 متن پشتیبانی","aset:support_text",style="primary")],[btn(f"🔒 جوین اجباری: {onoff(f)}","atog:force_join",style="primary")],[btn("📢 کانال قفل اجباری","channel_admin",style="primary")],[btn(f"🛠 حالت تعمیرات: {onoff(m)}","atog:maintenance",style="danger")],[btn("🏠 منوی اصلی ربات","home",style="danger")]])
def admin_back(c="admin"): return markup([[btn("🔙 بازگشت به پنل",c,style="danger")]])
def fivesim_admin_kb(has): return markup([[btn("✏️ ثبت / تغییر API Key","aset:fivesim_api",style="primary")],[btn("🌐 ورود به سایت 5Sim",url="https://5sim.net",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def zibal_admin_kb(sandbox,has): return markup([[btn("✏️ ثبت / تغییر Merchant ID","aset:zibal_merchant",style="primary")],[btn(f"🧪 حالت تست: {onoff(sandbox)}","atog:zibal_sandbox",style="primary")],[btn("🌐 ورود به پنل زرین‌پال",url="https://www.zarinpal.com",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def price_admin_kb(): return markup([[btn("💱 نرخ تبدیل","aset:rate",style="primary"),btn("📈 درصد سود","aset:profit_percent",style="primary")],[btn("🛡 نگهبان نرخ دلار","market_admin",style="primary")],[btn("⬇️ حداقل شارژ","aset:min_deposit",style="primary"),btn("⬆️ حداکثر شارژ","aset:max_deposit",style="primary")],[btn("🎁 درصد پاداش دعوت","aset:referral_percent",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def market_admin_kb(a,b): return admin_back("panel_price")
def user_manage_kb(uid,banned): return markup([[btn("➕ افزایش موجودی",f"ubal:{uid}:add",style="success"),btn("➖ کسر موجودی",f"ubal:{uid}:sub",style="danger")],[btn("✅ رفع مسدودی" if banned else "🚫 مسدود کردن",f"uban:{uid}",style="danger")],[btn("🔍 جستجوی کاربر دیگر","adm_user",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def broadcast_confirm_kb(): return markup([[btn("✅ ارسال برای همه","bc_send",style="success")],[btn("❌ انصراف","admin",style="danger")]])
def sintel_main_menu(): return markup([[btn("👥 خدمات تلگرام","sintel_telegram",style="success")],[btn("📸 خدمات اینستاگرام","sintel_instagram",style="success")],[btn("📦 سفارشات من","sintel_orders",style="primary")],[btn("🏠 منوی اصلی","home",style="danger")]])
def sintel_platform_menu(p):
    from services.sintel_catalog import SERVICE_CATEGORIES
    return markup([[btn(f"{i['emoji']} {i['title']}",f"stsc:{p}:{k}",style="primary")] for k,i in SERVICE_CATEGORIES.get(p,{}).get("subcategories",{}).items()]+[[btn("🔙 بازگشت","home",style="danger")]])
def sintel_services_list(ss): return markup([[btn(f"{s.get('name','سرویس')[:38]} | حداقل {s.get('min_quantity',0):,}",f"stlg:{s['service_id']}",style="primary")] for s in ss]+[[btn("🔙 بازگشت","home",style="danger")]])
def sintel_confirm_kb(ok): return markup([[btn("✅ ثبت سفارش","sintel_buy",style="success")] if ok else [btn("💳 شارژ کیف پول","sintel_wallet",style="success")],[btn("🔙 بازگشت","home",style="danger")]])
def sintel_orders_kb(): return markup([[btn("🔌 خرید سرویس جدید","sintel_telegram",style="success")],[btn("🏠 منوی اصلی","home",style="danger")]])
def sintel_order_detail_kb(i,s): return markup([[btn("🔄 بروزرسانی وضعیت",f"stch:{i}",style="primary")],[btn("🔙 سفارشات خدمات","sintel_orders",style="danger")],[btn("🏠 منوی اصلی","home",style="danger")]])
def sintel_admin_menu(s): return markup([[btn("🔑 تنظیم / تغییر API","sintel_set_api",style="primary")],[btn(f"🔌 فعال/غیرفعال: {'روشن' if s.get('enabled') else 'خاموش'}","sintel_toggle",style="success")],[btn("🔄 تست اتصال","sintel_test_connection",style="primary")],[btn("🔄 همگام‌سازی کاتالوگ","sintel_sync_catalog",style="success")],[btn("📦 مشاهده کاتالوگ","sintel_view_catalog",style="primary")],[btn("📈 تنظیم درصد سود","sintel_set_profit",style="primary")],[btn("🔙 بازگشت به پنل","admin",style="danger")]])
def sintel_catalog_menu(): return markup([[btn("👥 کاتالوگ تلگرام","sintel_cat:telegram",style="primary")],[btn("📸 کاتالوگ اینستاگرام","sintel_cat:instagram",style="primary")],[btn("🔙 بازگشت به پنل سینتل","panel_sintel",style="danger")]])
def sintel_admin_back(): return markup([[btn("🔙 بازگشت به پنل سینتل","panel_sintel",style="danger")]])
