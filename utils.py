"""SimPars utility helpers."""
from __future__ import annotations
import html, math
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
import texts
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
def esc(value) -> str: return html.escape(str(value or ""))
def phone_ltr(value) -> str: return "\u2066" + esc(str(value or "—")) + "\u2069"
def to_en_digits(value: str) -> str: return (value or "").translate(_DIGITS)
def parse_number(value: str) -> float | None:
    clean=to_en_digits(value).replace(",","").replace("٬","").replace(" ","").strip()
    try: number=float(clean)
    except ValueError: return None
    return None if math.isnan(number) or math.isinf(number) else number
def flag(iso: str) -> str:
    iso=(iso or "").lower()
    if len(iso)!=2 or not iso.isalpha(): return "🌐"
    return "".join(chr(0x1F1E6+ord(ch)-ord("a")) for ch in iso)
def country_title(code: str, countries: dict | None = None) -> str:
    info=(countries or {}).get(code) or {}; iso_map=info.get("iso") or {}; iso=next(iter(iso_map), "") if isinstance(iso_map,dict) else ""
    name=texts.COUNTRY_EN.get(code) or info.get("text_en") or code.replace("_", " ").replace("-", " ").title()
    return f"{flag(iso)} {name}"
def service_title(code: str) -> str:
    emoji,title=texts.SERVICE_MAP.get(code,("📱",code.capitalize())); return f"{emoji} {title}"
def calc_price(cost: float, rate: float, profit: float) -> int:
    raw=float(cost)*float(rate)*(1+float(profit)/100); return max(1000,int(math.ceil(raw/100.0))*100)
def mask(value: str) -> str:
    if not value: return "ثبت نشده"
    return value[:2]+"••••" if len(value)<=10 else value[:6]+"••••"+value[-4:]
async def safe_edit(call: CallbackQuery,text: str,reply_markup=None) -> None:
    try: await call.message.edit_text(text,reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc): return
        await call.message.answer(text,reply_markup=reply_markup)
