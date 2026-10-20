"""SimPars utility helpers."""
from __future__ import annotations
import html, math
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
import texts
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_COUNTRY_FA={"russia":"روسیه","usa":"آمریکا","england":"انگلیس","canada":"کانادا","germany":"آلمان","france":"فرانسه","netherlands":"هلند","italy":"ایتالیا","spain":"اسپانیا","portugal":"پرتغال","sweden":"سوئد","finland":"فنلاند","poland":"لهستان","romania":"رومانی","estonia":"استونی","latvia":"لتونی","lithuania":"لیتوانی","ukraine":"اوکراین","georgia":"گرجستان","armenia":"ارمنستان","azerbaijan":"آذربایجان","kazakhstan":"قزاقستان","uzbekistan":"ازبکستان","kyrgyzstan":"قرقیزستان","tajikistan":"تاجیکستان","turkey":"ترکیه","afghanistan":"افغانستان","pakistan":"پاکستان","india":"هند","bangladesh":"بنگلادش","china":"چین","hongkong":"هنگ‌کنگ","indonesia":"اندونزی","malaysia":"مالزی","philippines":"فیلیپین","vietnam":"ویتنام","thailand":"تایلند","cambodia":"کامبوج","myanmar":"میانمار","laos":"لائوس","egypt":"مصر","nigeria":"نیجریه","kenya":"کنیا","southafrica":"آفریقای جنوبی","morocco":"مراکش","ghana":"غنا","mexico":"مکزیک","brazil":"برزیل","colombia":"کلمبیا","argentina":"آرژانتین","chile":"شیلی","peru":"پرو","iraq":"عراق","saudiarabia":"عربستان سعودی","israel":"اسرائیل","japan":"ژاپن","southkorea":"کره جنوبی","australia":"استرالیا","belgium":"بلژیک","austria":"اتریش","czech":"جمهوری چک","greece":"یونان","ireland":"ایرلند","serbia":"صربستان","bulgaria":"بلغارستان","moldova":"مولداوی","belarus":"بلاروس","mongolia":"مغولستان","nepal":"نپال","srilanka":"سریلانکا"}
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
    code_key=str(code or "").lower(); info=(countries or {}).get(code) or {}; iso_map=info.get("iso") or {}; iso=next(iter(iso_map), "") if isinstance(iso_map,dict) else ""
    fa_map=getattr(texts,"COUNTRY_FA",{}) or {}; name=_COUNTRY_FA.get(code_key) or fa_map.get(code_key) or texts.COUNTRY_EN.get(code_key) or info.get("text_en") or code_key.replace("_", " ").replace("-", " ").title()
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
