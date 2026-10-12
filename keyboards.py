"""SimPars inline keyboards."""
from __future__ import annotations

from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import texts
from config import CHANNEL_USERNAME, INSTAGRAM_ID, OWNER_USERNAME


def btn(text: str, cb: str | None = None, url: str | None = None) -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=cb or "noop")


def markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def onoff(value: str) -> str:
    return "✅ روشن" if value == "1" else "❌ خاموش"


CHANNEL_URL = "https://t.me/" + CHANNEL_USERNAME.lstrip("@")
OWNER_URL = f"https://t.me/{OWNER_USERNAME}"
INSTAGRAM_URL = f"https://instagram.com/{INSTAGRAM_ID}"


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [btn("🛒 خرید شماره مجازی", "buy")],
        [btn("💰 کیف پول", "wallet"), btn("👤 حساب من", "account")],
        [btn("📦 سفارش‌های من", "orders"), btn("🎁 دعوت دوستان", "referral")],
        [btn("💬 پشتیبانی", "support"), btn("📚 راهنما", "help")],
        [btn("📢 کانال ما", url=CHANNEL_URL), btn("📸 اینستاگرام", url=INSTAGRAM_URL)],
    ]
    if is_admin:
        rows.append([btn("⚙️ پنل مدیریت", "admin")])
    return markup(rows)


def back_main() -> InlineKeyboardMarkup:
    return markup([[btn("🏠 بازگشت به منوی اصلی", "home")]])


def back_to(cb: str, text: str = "🔙 بازگشت") -> InlineKeyboardMarkup:
    return markup([[btn(text, cb)], [btn("🏠 منوی اصلی", "home")]])


def join_kb() -> InlineKeyboardMarkup:
    return markup([
        [btn("📢 عضویت در کانال سیم‌پارس", url=CHANNEL_URL)],
        [btn("✅ عضو شدم", "joined")],
    ])


def services_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, emoji, title in texts.SERVICES:
        row.append(btn(f"{emoji} {title}", f"srv:{code}:0"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([btn("🏠 منوی اصلی", "home")])
    return markup(rows)


def storefront_kb(products: list[str]) -> InlineKeyboardMarkup:
    return markup([
        [btn("💎 بهترین قیمت‌ها", "cat:cheap"), btn("💰 اقتصادی", "cat:economic")],
        [btn("🌍 همه کشورها و اپراتورها", "cat:all")],
        [btn("🏠 منوی اصلی", "home")],
    ])


def product_kb(products: list[str], category: str = "all") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for product in products:
        known = texts.SERVICE_MAP.get(product)
        label = (
            f"{known[0]} {known[1]}"
            if known
            else f"🌐 {product.replace('_', ' ').replace('-', ' ').title()}"
        )
        row.append(btn(label, f"srv:{product}:0"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.extend([
        [btn("⬅️ دسته‌بندی خرید", "buy")],
        [btn("🏠 منوی اصلی", "home")],
    ])
    return markup(rows)


def countries_kb(product: str, items: list[tuple[str, str]], page: int, pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for country, label in items:
        row.append(btn(label, f"cn:{product}:{country}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(btn("◀️ قبلی", f"srv:{product}:{page - 1}"))
    nav.append(btn(f"📄 {page + 1}/{pages}", "noop"))
    if page < pages - 1:
        nav.append(btn("بعدی ▶️", f"srv:{product}:{page + 1}"))
    rows.extend([
        nav,
        [btn("🔄 بروزرسانی قیمت‌ها", f"srv:{product}:{page}")],
        [btn("🔙 انتخاب سرویس", "buy"), btn("🏠 منوی اصلی", "home")],
    ])
    return markup(rows)


def operators_kb(product: str, country: str, items: list[tuple[str, int, int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for operator, price, count in items:
        title = "خودکار" if operator in ("auto", "any") else operator
        rows.append([
            btn(
                f"📡 {title} | 💰 {price:,} تومان | 📦 {count}",
                f"op:{product}:{country}:{operator}",
            )
        ])
    rows.extend([
        [btn("🔙 بازگشت به کشورها", f"srv:{product}:0")],
        [btn("🏠 منوی اصلی", "home")],
    ])
    return markup(rows)


def confirm_kb(product: str, country: str, operator: str, enough: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if enough:
        rows.append([btn("✅ تأیید و خرید", f"ok:{product}:{country}:{operator}")])
    else:
        rows.append([btn("💳 شارژ کیف پول", "wallet")])
    rows.extend([
        [btn("🔙 انتخاب اپراتور", f"cn:{product}:{country}")],
        [btn("🏠 منوی اصلی", "home")],
    ])
    return markup(rows)


def order_kb(order_id: int) -> InlineKeyboardMarkup:
    return markup([
        [btn("🔄 بررسی دریافت کد", f"chk:{order_id}")],
        [btn("❌ لغو و بازگشت وجه", f"cnl:{order_id}")],
    ])


def order_received_kb(order_id: int) -> InlineKeyboardMarkup:
    return markup([
        [btn("🔄 بررسی پیامک جدید", f"chk:{order_id}")],
        [btn("✅ اتمام سفارش", f"fin:{order_id}")],
        [btn("🏠 منوی اصلی", "home")],
    ])


def wallet_kb() -> InlineKeyboardMarkup:
    amounts = [50_000, 100_000, 200_000, 500_000]
    return markup([
        [btn(f"💵 {amounts[0]:,} تومان", f"dep:{amounts[0]}"), btn(f"💵 {amounts[1]:,} تومان", f"dep:{amounts[1]}")],
        [btn(f"💵 {amounts[2]:,} تومان", f"dep:{amounts[2]}"), btn(f"💵 {amounts[3]:,} تومان", f"dep:{amounts[3]}")],
        [btn("✍️ مبلغ دلخواه", "dep_custom")],
        [btn("🏠 منوی اصلی", "home")],
    ])


def payment_kb(url: str, track_id: str) -> InlineKeyboardMarkup:
    return markup([
        [btn("💳 پرداخت آنلاین", url=url)],
        [btn("✅ پرداخت کردم، بررسی شود", f"vfy:{track_id}")],
        [btn("🏠 منوی اصلی", "home")],
    ])


def cancel_kb(cb: str = "home") -> InlineKeyboardMarkup:
    return markup([[btn("❌ انصراف", cb)]])


def support_kb() -> InlineKeyboardMarkup:
    return markup([
        [btn("👨‍💻 ارتباط با پشتیبانی", url=OWNER_URL)],
        [btn("📢 کانال", url=CHANNEL_URL), btn("📸 اینستاگرام", url=INSTAGRAM_URL)],
        [btn("🏠 منوی اصلی", "home")],
    ])


def referral_kb(link: str) -> InlineKeyboardMarkup:
    share = f"https://t.me/share/url?url={quote(link)}&text={quote('📱 با سیم‌پارس شماره مجازی بگیر!')}"
    return markup([[btn("📤 اشتراک‌گذاری لینک", url=share)], [btn("🏠 منوی اصلی", "home")]])


def admin_menu(force_join: str, maintenance: str) -> InlineKeyboardMarkup:
    return markup([
        [btn("📊 آمار و گزارشات", "adm_stats")],
        [btn("🔑 تنظیمات 5Sim", "panel_5sim"), btn("💳 درگاه زرین‌پال", "panel_zibal")],
        [btn("💹 قیمت‌گذاری و مالی", "panel_price"), btn("👥 مدیریت کاربران", "adm_user")],
        [btn("📢 پیام همگانی", "adm_bc"), btn("📝 متن پشتیبانی", "aset:support_text")],
        [btn(f"🔒 جوین اجباری: {onoff(force_join)}", "atog:force_join")],
        [btn(f"🛠 حالت تعمیرات: {onoff(maintenance)}", "atog:maintenance")],
        [btn("🏠 منوی اصلی ربات", "home")],
    ])


def admin_back(cb: str = "admin") -> InlineKeyboardMarkup:
    return markup([[btn("🔙 بازگشت به پنل", cb)]])


def fivesim_admin_kb(has_key: bool) -> InlineKeyboardMarkup:
    rows = [[btn("✏️ ثبت / تغییر API Key", "aset:fivesim_api")]]
    if has_key:
        rows.append([btn("🔄 بروزرسانی موجودی", "panel_5sim"), btn("🗑 حذف API", "adel:fivesim_api")])
    rows.extend([
        [btn("🌐 ورود به سایت 5Sim", url="https://5sim.net")],
        [btn("🔙 بازگشت به پنل", "admin")],
    ])
    return markup(rows)


def zibal_admin_kb(sandbox: str, has_merchant: bool) -> InlineKeyboardMarkup:
    rows = [
        [btn("✏️ ثبت / تغییر Merchant ID", "aset:zibal_merchant")],
        [btn(f"🧪 حالت تست: {onoff(sandbox)}", "atog:zibal_sandbox")],
        [btn("🌐 تنظیم آدرس بازگشت", "aset:zibal_callback"), btn("♻️ آدرس پیش‌فرض", "adel:zibal_callback")],
    ]
    if has_merchant:
        rows.append([btn("🗑 حذف Merchant ID", "adel:zibal_merchant")])
    rows.extend([
        [btn("🌐 ورود به پنل زرین‌پال", url="https://www.zarinpal.com")],
        [btn("🔙 بازگشت به پنل", "admin")],
    ])
    return markup(rows)


def price_admin_kb() -> InlineKeyboardMarkup:
    return markup([
        [btn("💱 نرخ تبدیل", "aset:rate"), btn("📈 درصد سود", "aset:profit_percent")],
        [btn("🛡 نگهبان نرخ دلار", "market_admin")],
        [btn("⬇️ حداقل شارژ", "aset:min_deposit"), btn("⬆️ حداکثر شارژ", "aset:max_deposit")],
        [btn("🎁 درصد پاداش دعوت", "aset:referral_percent")],
        [btn("🔙 بازگشت به پنل", "admin")],
    ])


def market_admin_kb(has_key: bool, has_url: bool) -> InlineKeyboardMarkup:
    return markup([
        [btn("🔐 ثبت / تغییر کلید API", "market_set_key")],
        [btn("🌐 ثبت / تغییر آدرس API", "market_set_url")],
        [btn("🔄 تست و بروزرسانی نرخ", "market_refresh")],
        [btn("🔙 بازگشت به قیمت‌گذاری", "panel_price")],
    ])


def user_manage_kb(uid: int, banned: bool) -> InlineKeyboardMarkup:
    return markup([
        [btn("➕ افزایش موجودی", f"ubal:{uid}:add"), btn("➖ کسر موجودی", f"ubal:{uid}:sub")],
        [btn("✅ رفع مسدودی" if banned else "🚫 مسدود کردن", f"uban:{uid}")],
        [btn("🔍 جستجوی کاربر دیگر", "adm_user")],
        [btn("🔙 بازگشت به پنل", "admin")],
    ])


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return markup([
        [btn("✅ ارسال برای همه", "bc_send")],
        [btn("❌ انصراف", "admin")],
    ])
