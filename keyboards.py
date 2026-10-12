"""SimPars inline keyboards with Telegram Bot API 9.4 styles."""
from __future__ import annotations
from urllib.parse import quote
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import texts
from config import CHANNEL_USERNAME, INSTAGRAM_ID, OWNER_USERNAME, PREMIUM_EMOJI_DANGER, PREMIUM_EMOJI_PRIMARY, PREMIUM_EMOJI_SUCCESS

CHANNEL_URL = "https://t.me/" + CHANNEL_USERNAME.lstrip("@")
OWNER_URL = f"https://t.me/{OWNER_USERNAME.lstrip('@')}"
INSTAGRAM_URL = f"https://instagram.com/{INSTAGRAM_ID.lstrip('@')}"


def _style(text: str, callback: str | None, url: str | None = None) -> str | None:
    value = f"{text} {callback or ''} {url or ''}".lower()
    if "instagram" in value or "کانال ما" in value or any(word in value for word in ("منوی اصلی", "main", "home", "بازگشت", "انصراف", "لغو")):
        return "danger"
    if "تومان" in value or "قیمت" in value:
        return "danger"
    if "بعدی" in value or "next" in value or any(word in value for word in ("خرید", "پرداخت", "تأیید", "شارژ", "اشتراک")):
        return "success"
    if any(word in value for word in ("راهنما", "پشتیبانی")) or callback in {"account", "wallet", "referral", "orders"}:
        return "primary"
    if "انتخاب پلتفرم" in value:
        return "danger"
    if "انتخاب کشور" in value or (callback or "").startswith(("srv:", "cat:", "cn:")):
        return "primary"
    return None


def _emoji_for(style: str | None) -> str | None:
    return {"success": PREMIUM_EMOJI_SUCCESS, "danger": PREMIUM_EMOJI_DANGER, "primary": PREMIUM_EMOJI_PRIMARY}.get(style)


def btn(text: str, callback: str | None = None, url: str | None = None, *, style: str | None = None, icon_custom_emoji_id: str | None = None) -> InlineKeyboardButton:
    resolved_style = style or _style(text, callback, url)
    return InlineKeyboardButton(text=text, url=url, callback_data=None if url else (callback or "noop"), style=resolved_style, icon_custom_emoji_id=icon_custom_emoji_id or _emoji_for(resolved_style))


def markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def onoff(value: str) -> str:
    return "✅ روشن" if value == "1" else "❌ خاموش"


def _platform_name(product: str) -> str:
    known = texts.SERVICE_MAP.get(product)
    emoji, title = known if known else ("🔹", product.replace("_", " ").replace("-", " "))
    title = " ".join(word[:1].upper() + word[1:].lower() for word in title.split())
    return f"{emoji} {title}"


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [[btn("🛒 خرید شماره مجازی", "buy", style="success")], [btn("💰 کیف پول", "wallet", style="primary"), btn("👤 حساب من", "account", style="primary")], [btn("📦 سفارش‌های من", "orders", style="primary"), btn("🎁 دعوت دوستان", "referral", style="primary")], [btn("💬 پشتیبانی", "support", style="primary"), btn("📚 راهنما", "help", style="primary")], [btn("📢 کانال ما", url=CHANNEL_URL, style="danger"), btn("📸 اینستاگرام", url=INSTAGRAM_URL, style="danger")]]
    if is_admin:
        rows.append([btn("⚙️ پنل مدیریت", "admin", style="primary")])
    return markup(rows)


def back_main() -> InlineKeyboardMarkup:
    return markup([[btn("🏠 بازگشت به منوی اصلی", "home", style="danger")]])


def back_to(callback: str, text: str = "🔙 بازگشت") -> InlineKeyboardMarkup:
    return markup([[btn(text, callback, style="danger")], [btn("🏠 منوی اصلی", "home", style="danger")]])


def join_kb() -> InlineKeyboardMarkup:
    return markup([[btn("📢 عضویت در کانال سیم‌پارس", url=CHANNEL_URL, style="primary")], [btn("✅ عضو شدم", "joined", style="success")]])


def services_kb() -> InlineKeyboardMarkup:
    return product_kb([code for code, _, _ in texts.SERVICES])


def storefront_kb(products: list[str] | None = None) -> InlineKeyboardMarkup:
    return markup([[btn("💎 خرید اقتصادی", "cat:economic:0", style="primary")], [btn("🏠 منوی اصلی", "home", style="danger")]])


def product_kb(products: list[str], category: str = "economic", page: int = 0, pages: int = 1) -> InlineKeyboardMarkup:
    rows, row = [], []
    for product in products:
        row.append(btn(_platform_name(product), f"srv:{product}:0:{category}", style="primary"))
        if len(row) == 3:
            rows.append(row); row = []
    if row: rows.append(row)
    navigation = []
    if page > 0: navigation.append(btn("⬅️ قبلی", f"cat:{category}:{page - 1}", style="primary"))
    navigation.append(btn(f"📄 {page + 1}/{pages}", "noop", style="success"))
    if page < pages - 1: navigation.append(btn("بعدی ➡️", f"cat:{category}:{page + 1}", style="success"))
    rows.extend([navigation, [btn("🔙 بازگشت", "buy", style="danger")], [btn("🏠 منوی اصلی", "home", style="danger")]])
    return markup(rows)


def countries_kb(product: str, items: list[tuple[str, str, str]], page: int, pages: int) -> InlineKeyboardMarkup:
    rows = [[btn(country, cb, style="primary"), btn(price, "noop", style="danger"), btn("🛒 خرید", cb, style="success")] for country, price, cb in items]
    navigation = []
    if page > 0: navigation.append(btn("⬅️ قبلی", f"srv:{product}:{page - 1}:economic", style="primary"))
    navigation.append(btn(f"📄 {page + 1}/{pages}", "noop", style="primary"))
    if page < pages - 1: navigation.append(btn("بعدی ➡️", f"srv:{product}:{page + 1}:economic", style="success"))
    rows.extend([navigation, [btn("🔄 بروزرسانی قیمت‌ها", f"srv:{product}:{page}:economic", style="primary")], [btn("🔴 انتخاب پلتفرم", "cat:economic:0", style="danger"), btn("🏠 منوی اصلی", "home", style="danger")]])
    return markup(rows)


def operators_kb(product: str, country: str, items: list[object], page: int, pages: int) -> InlineKeyboardMarkup:
    start = page * 12; visible = items[start:start + 12]; rows, row = [], []
    for local_index, _ in enumerate(visible):
        row.append(btn(str(start + local_index + 1), f"op:{product}:{country}:{start + local_index}", style="primary"))
        if len(row) == 4: rows.append(row); row = []
    if row: rows.append(row)
    navigation = []
    if page > 0: navigation.append(btn("⬅️ قبلی", f"ops:{product}:{country}:{page - 1}", style="primary"))
    navigation.append(btn(f"📄 {page + 1}/{pages}", "noop", style="primary"))
    if page < pages - 1: navigation.append(btn("بعدی ➡️", f"ops:{product}:{country}:{page + 1}", style="success"))
    rows.extend([navigation, [btn("بازگشت به کشورها", f"srv:{product}:0:economic", style="danger")], [btn("🏠 منوی اصلی", "home", style="danger")]])
    return markup(rows)


def confirm_kb(product: str, country: str, operator: str, enough: bool) -> InlineKeyboardMarkup:
    rows = [[btn("✅ تأیید و خرید", f"ok:{product}:{country}:{operator}", style="success")]] if enough else [[btn("💳 شارژ کیف پول", "wallet", style="success")]]
    rows.extend([[btn("انتخاب کشور", f"srv:{product}:0:economic", style="primary")], [btn("🏠 منوی اصلی", "home", style="danger")]])
    return markup(rows)


def order_kb(order_id: int | str) -> InlineKeyboardMarkup:
    return markup([[btn("🔄 بررسی دریافت کد", f"chk:{order_id}", style="primary")], [btn("❌ لغو و بازگشت وجه", f"cnl:{order_id}", style="danger")]])


def order_received_kb(order_id: int | str) -> InlineKeyboardMarkup:
    return markup([[btn("🔄 بررسی پیامک جدید", f"chk:{order_id}", style="primary")], [btn("✅ اتمام سفارش", f"fin:{order_id}", style="success")], [btn("🏠 منوی اصلی", "home", style="danger")]])


def wallet_kb() -> InlineKeyboardMarkup:
    amounts = [50000, 100000, 200000, 500000]
    return markup([[btn(f"💵 {amounts[0]:,} تومان", f"dep:{amounts[0]}", style="success"), btn(f"💵 {amounts[1]:,} تومان", f"dep:{amounts[1]}", style="success")], [btn(f"💵 {amounts[2]:,} تومان", f"dep:{amounts[2]}", style="success"), btn(f"💵 {amounts[3]:,} تومان", f"dep:{amounts[3]}", style="success")], [btn("✍️ مبلغ دلخواه", "dep_custom", style="primary")], [btn("🏠 منوی اصلی", "home", style="danger")]])


def payment_kb(url: str, track_id: str) -> InlineKeyboardMarkup:
    return markup([[btn("💳 پرداخت آنلاین", url=url, style="success")], [btn("✅ پرداخت کردم، بررسی شود", f"vfy:{track_id}", style="success")], [btn("🏠 منوی اصلی", "home", style="danger")]])


def cancel_kb(callback: str = "home") -> InlineKeyboardMarkup:
    return markup([[btn("انصراف", callback, style="danger")]])


def support_kb() -> InlineKeyboardMarkup:
    return markup([[btn("💬 ارتباط با پشتیبانی", url=OWNER_URL, style="primary")], [btn("📢 کانال", url=CHANNEL_URL, style="success"), btn("📸 اینستاگرام", url=INSTAGRAM_URL, style="success")], [btn("🏠 منوی اصلی", "home", style="danger")]])


def referral_kb(link: str) -> InlineKeyboardMarkup:
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote('با سیم‌پارس شماره مجازی بگیر!')}"
    return markup([[btn("📤 اشتراک‌گذاری لینک", url=share_url, style="success")], [btn("🏠 منوی اصلی", "home", style="danger")]])


def admin_menu(force_join: str, maintenance: str) -> InlineKeyboardMarkup:
    return markup([[btn("📊 آمار و گزارشات", "adm_stats", style="primary")], [btn("🔑 تنظیمات 5Sim", "panel_5sim", style="primary"), btn("💳 درگاه زرین‌پال", "panel_zibal", style="primary")], [btn("💹 قیمت‌گذاری و مالی", "panel_price", style="primary"), btn("👥 مدیریت کاربران", "adm_user", style="primary")], [btn("📢 پیام همگانی", "adm_bc", style="primary"), btn("📝 متن پشتیبانی", "aset:support_text", style="primary")], [btn(f"🔒 جوین اجباری: {onoff(force_join)}", "atog:force_join", style="primary")], [btn("📢 کانال قفل اجباری", "aset:force_join_channel", style="primary")], [btn(f"🛠 حالت تعمیرات: {onoff(maintenance)}", "atog:maintenance", style="danger")], [btn("🏠 منوی اصلی ربات", "home", style="danger")]])


def admin_back(callback: str = "admin") -> InlineKeyboardMarkup:
    return markup([[btn("🔙 بازگشت به پنل", callback, style="danger")]])


def fivesim_admin_kb(has_key: bool) -> InlineKeyboardMarkup:
    return markup([[btn("✏️ ثبت / تغییر API Key", "aset:fivesim_api", style="primary")], [btn("🌐 ورود به سایت 5Sim", url="https://5sim.net", style="primary")], [btn("🔙 بازگشت به پنل", "admin", style="danger")]])


def zibal_admin_kb(sandbox: str, has_merchant: bool) -> InlineKeyboardMarkup:
    return markup([[btn("✏️ ثبت / تغییر Merchant ID", "aset:zibal_merchant", style="primary")], [btn(f"🧪 حالت تست: {onoff(sandbox)}", "atog:zibal_sandbox", style="primary")], [btn("🌐 ورود به پنل زرین‌پال", url="https://www.zarinpal.com", style="primary")], [btn("🔙 بازگشت به پنل", "admin", style="danger")]])


def price_admin_kb() -> InlineKeyboardMarkup:
    return markup([[btn("💱 نرخ تبدیل", "aset:rate", style="primary"), btn("📈 درصد سود", "aset:profit_percent", style="primary")], [btn("🛡 نگهبان نرخ دلار", "market_admin", style="primary")], [btn("⬇️ حداقل شارژ", "aset:min_deposit", style="primary"), btn("⬆️ حداکثر شارژ", "aset:max_deposit", style="primary")], [btn("🎁 درصد پاداش دعوت", "aset:referral_percent", style="primary")], [btn("🔙 بازگشت به پنل", "admin", style="danger")]])


def market_admin_kb(has_key: bool, has_url: bool) -> InlineKeyboardMarkup:
    return markup([[btn("🔐 ثبت / تغییر کلید API", "market_set_key", style="primary")], [btn("🌐 ثبت / تغییر آدرس API", "market_set_url", style="primary")], [btn("🔄 تست و بروزرسانی نرخ", "market_refresh", style="success")], [btn("🔙 بازگشت به قیمت‌گذاری", "panel_price", style="danger")]])


def user_manage_kb(uid: int | str, banned: bool) -> InlineKeyboardMarkup:
    return markup([[btn("➕ افزایش موجودی", f"ubal:{uid}:add", style="success"), btn("➖ کسر موجودی", f"ubal:{uid}:sub", style="danger")], [btn("✅ رفع مسدودی" if banned else "🚫 مسدود کردن", f"uban:{uid}", style="danger")], [btn("🔍 جستجوی کاربر دیگر", "adm_user", style="primary")], [btn("🔙 بازگشت به پنل", "admin", style="danger")]])


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return markup([[btn("✅ ارسال برای همه", "bc_send", style="success")], [btn("❌ انصراف", "admin", style="danger")]])
