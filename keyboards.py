"""Inline keyboards with consistent Persian navigation."""
from __future__ import annotations
from urllib.parse import quote
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import texts
from config import CHANNEL_USERNAME, INSTAGRAM_ID, OWNER_USERNAME
CHANNEL_URL="https://t.me/"+CHANNEL_USERNAME.lstrip("@"); OWNER_URL=f"https://t.me/{OWNER_USERNAME.lstrip('@')}"; INSTAGRAM_URL=f"https://instagram.com/{INSTAGRAM_ID.lstrip('@')}"
# Telegram inline buttons do not support custom background colours. These markers
# provide a stable green/blue/orange visual key for the three country columns.
COLUMN_STYLES=("primary","success","danger")
COUNTRY_COLUMN_MARKERS=("🟩","🟦","🟧")
PLATFORM_EMOJI={"telegram":"✈️","instagram":"🌸","whatsapp":"💚","openai":"🤖","google":"🔎","facebook":"📘","twitter":"🐦","tiktok":"🎵","discord":"🎮","microsoft":"🪟","amazon":"📦","snapchat":"👻","viber":"🪻","signal":"🛡","linkedin":"💼","yahoo":"📨","netflix":"🎬","paypal":"💳","steam":"🕹","imo":"🗨","line":"🫧","wechat":"🧧","uber":"🚕","apple":"🍏","yandex":"🟥","binance":"🪙","ebay":"🛍","airbnb":"🏠","spotify":"🎧","twitch":"🟪","mailru":"📬","proton":"🔐","bolt":"⚡️","revolut":"🏦","tinder":"🔥","bumble":"🐝","nike":"👟","other":"🌐"}
def btn(text,callback=None,url=None,*,style=None,icon_custom_emoji_id=None): return InlineKeyboardButton(text=text,url=url,callback_data=None if url else (callback or "noop"),style=style,icon_custom_emoji_id=icon_custom_emoji_id)
def markup(rows): return InlineKeyboardMarkup(inline_keyboard=rows)
def onoff(value): return "✅ روشن" if value=="1" else "❌ خاموش"
def main_menu(is_admin=False):
    rows=[[btn("📱 خرید شماره مجازی","buy",style="success")],[btn("📣 خدمات شبکه‌های اجتماعی","sintel",style="success")],[btn("💰 کیف پول","wallet",style="primary"),btn("👤 حساب من","account",style="primary")],[btn("📦 سفارش‌های من","orders",style="primary"),btn("📦 سفارشات خدمات","sintel_orders",style="primary")],[btn("🎁 دعوت دوستان","referral",style="primary"),btn("💬 پشتیبانی","support",style="primary")],[btn("📚 راهنما","help",style="primary")],[btn("📢 کانال ما",url=CHANNEL_URL,style="danger"),btn("📸 اینستاگرام",url=INSTAGRAM_URL,style="danger")]]
    if is_admin: rows.append([btn("⚙️ پنل مدیریت","admin",style="primary")])
    return markup(rows)
def back_main(): return markup([[btn("🏠 بازگشت به منوی اصلی","home",style="danger")]])
def back_to(c,text="🔙 بازگشت"): return markup([[btn(text,c,style="primary")],[btn("🏠 منوی اصلی","home",style="primary")]])
def cancel_kb(c="home"): return markup([[btn("انصراف",c,style="primary")]])
def join_kb(): return markup([[btn("📢 عضویت در کانال سیم‌پارس",url=CHANNEL_URL,style="primary")],[btn("✅ عضو شدم","joined",style="success")]])
def services_kb(): return platforms_kb([x[0] for x in texts.SERVICES])
def _platform_name(p):
    code=str(p or "").strip().lower(); emoji,title=texts.SERVICE_MAP.get(code,(None,code.replace("_"," ").replace("-"," ").title()))
    return f"{PLATFORM_EMOJI.get(code) or emoji or '🔸'} {title}"
def _platform_grid(products,category):
    """سه‌ستونه و بر پایهٔ پلتفرم‌های واقعاً برگشتی از کاتالوگ provider."""
    products=list(products or []); rows=[]
    for i in range(0,len(products),3): rows.append([btn(_platform_name(p),f"srv:{p}:0:{category}",style=COLUMN_STYLES[col]) for col,p in enumerate(products[i:i+3])])
    return rows
def platforms_kb(products,category="economic",page=0,pages=1):
    rows=_platform_grid(products,category); nav=[]
    if page>0: nav.append(btn("⬅️ صفحه قبل",f"cat:{category}:{page-1}",style="primary"))
    if pages>1:
        nav.append(btn(f"📄 {page+1}/{pages}","noop",style="primary"))
        if page<pages-1: nav.append(btn("صفحه بعد ➡️",f"cat:{category}:{page+1}",style="primary"))
    return markup(rows+([nav] if nav else [])+[_social_back("home",back_style="danger")])
def storefront_kb(products=None): return platforms_kb(products)
def product_kb(products,category="economic",page=0,pages=1): return platforms_kb(products,category,page,pages)
def countries_kb(product,items,page=0,pages=1):
    """اطلاعات هر کشور در سه ستون ثابت: کشور، قیمت، خرید.
    Telegram رنگ پس‌زمینهٔ سفارشی ندارد، پس نشانگرهای سبز/آبی/نارنجی را به‌کار می‌بریم.
    همهٔ سه دکمهٔ یک ردیف callback یکسان و مخصوص همان کشور دارند.
    """
    rows=[]
    for row_index,(name,price,cb) in enumerate(items):
        marker=COUNTRY_COLUMN_MARKERS[row_index % len(COUNTRY_COLUMN_MARKERS)]
        rows.append([btn(f"{marker} {name}",cb,style="primary"),btn(f"💰 {price}",cb,style="success"),btn("🛒 خرید",cb,style="danger")])
    nav=[]
    if page>0: nav.append(btn("⬅️ صفحه قبل",f"srv:{product}:{page-1}:economic",style="primary"))
    if pages>1:
        nav.append(btn(f"📄 {page+1}/{pages}","noop",style="primary"))
        if page<pages-1: nav.append(btn("صفحه بعد ➡️",f"srv:{product}:{page+1}:economic",style="primary"))
    return markup(rows+([nav] if nav else [])+[_social_back("buy",back_style="danger")])
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
def sintel_main_menu(): return markup([[btn("🛒 انتخاب خدمات","sintel_telegram",style="success")],[btn("📦 سفارشات من","sintel_orders",style="primary")],[btn("🏠 منوی اصلی","home",style="primary")]])
def sintel_platform_menu(p):
    from services.sintel_catalog import PLATFORM_LABELS
    e,t=PLATFORM_LABELS.get(p,("📱",p)); return markup([[btn(f"{e} {t}",f"stsc:{p}:all",style="danger")],_social_back("sintel")])
_QUALITY=(("⭐ پریمیوم",("premium","vip","پریمیوم","ویژه")),("💎 واقعی",("real","واقعی","ایرانی","iran")),("🔥 کیفیت بالا",("hq","high quality","کیفیت بالا","باکیفیت","با کیفیت")),("💰 اقتصادی",("cheap","ارزان","اقتصادی","فیک","fake")))
def _quality(s):
    t=" ".join(str(s.get(k) or "") for k in ("display_name","name","description","provider_category")).lower()
    return next((label for label,keys in _QUALITY if any(k in t for k in keys)),"✨ استاندارد")
def sintel_services_list(ss):
    rows=[]
    for s in ss:
        cb=f"stlg:{s['service_id']}"; name=(s.get('display_name') or s.get('name') or 'سرویس')[:28]
        rows.append([btn(name,cb,style=COLUMN_STYLES[0]),btn(_quality(s),cb,style=COLUMN_STYLES[1]),btn(f"حداقل {int(s.get('min_quantity') or 0):,}",cb,style=COLUMN_STYLES[2])])
    return markup(rows+[_social_back("sintel")])
def sintel_confirm_kb(ok):
    rows=[[btn("✅ تأیید سفارش","sintel_buy",style="success")] if ok else [btn("💳 شارژ کیف پول","sintel_wallet",style="success")]]; rows.append(_social_back("sintel")); return markup(rows)
def sintel_orders_kb(): return markup([[btn("🛒 خرید سرویس جدید","sintel",style="success")],[btn("🏠 منوی اصلی","home",style="primary")]])
def sintel_order_detail_kb(i,s): return markup([[btn("🔄 بروزرسانی وضعیت",f"stch:{i}",style="primary")],_social_back("sintel_orders")])
def sintel_admin_menu(s): return markup([[btn("🔑 تنطیم کلید API","sintel_set_api",style="primary")],[btn("🔌 بررسی اتصال پنلیکس","sintel_test_connection",style="primary")],[btn("📥 دریافت آخرین سرویس‌ها","sintel_sync_catalog",style="success")],[btn("🔄 بروزرسانی قیمت‌ها","panelix_prices",style="success")],[btn("📊 وضعیت همگام‌سازی","panelix_status",style="primary")],[btn("💰 تنطیم سود و قیمت فروش","panelix_set:panelix_profit_percent",style="primary")],[btn("💱 تنطیم واحد نرخ","panelix_set:panelix_rate_unit",style="primary"),btn("💵 تنطیم ارز","panelix_set:panelix_currency",style="primary")],[btn("⏱ تنطیم فاصله بروزرسانی","panelix_set:panelix_sync_interval",style="primary")],[btn("📋 گزارش خطاها","panelix_status",style="primary")],[btn("🔙 بازگشت به مدیریت پنلیکس","admin",style="primary")]])
def sintel_catalog_menu(): return markup([[btn("📦 کاتالوگ خدمات","sintel_telegram",style="primary")],[btn("🔙 بازگشت به مدیریت پنلیکس","panel_sintel",style="primary")]])
def sintel_admin_back(): return markup([[btn("🔙 بازگشت به مدیریت پنلیکس","panel_sintel",style="primary")]])
