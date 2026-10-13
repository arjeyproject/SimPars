"""وب‌سرور امن برای Callback و صفحه ورود به درگاه زرین‌پال."""
from __future__ import annotations

import html
import logging

from aiogram import Bot
from aiohttp import web

import database as db
from config import BOT_USERNAME
from services import zarinpal
from services.payments import is_sandbox, process_payment

log = logging.getLogger(__name__)
PAGE = """<!doctype html><html lang=\"fa\" dir=\"rtl\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>SimPars | نتیجه پرداخت</title><style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:Tahoma,sans-serif;background:linear-gradient(135deg,#123d31,#4e9279);color:#fff}}.card{{background:#ffffff1f;border:1px solid #ffffff40;border-radius:24px;padding:36px 28px;max-width:420px;width:88%;text-align:center;box-shadow:0 10px 40px #0005}}.icon{{font-size:64px}}h1{{font-size:22px}}p{{line-height:1.9;opacity:.9}}a{{display:inline-block;margin-top:16px;padding:12px 28px;border-radius:14px;background:#fff;color:#17352d;text-decoration:none;font-weight:bold}}</style></head><body><div class=\"card\"><div class=\"icon\">{icon}</div><h1>{title}</h1><p>{message}</p><a href=\"https://t.me/{bot}\">🤖 بازگشت به ربات</a></div></body></html>"""

# صفحه واسط: کاربر از دامنه خودمان به درگاه می‌رود تا زرین‌پال Referer را با
# دامنه ثبت‌شده تطبیق دهد (خطای -18). ریدایرکت 302 Referer را عوض نمی‌کند،
# برای همین از ناوبری سمت مرورگر (JS + دکمه) استفاده می‌شود.
REDIRECT_PAGE = """<!doctype html><html lang=\"fa\" dir=\"rtl\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"referrer\" content=\"origin\"><title>SimPars | انتقال به درگاه</title><style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:Tahoma,sans-serif;background:linear-gradient(135deg,#123d31,#4e9279);color:#fff}}.card{{background:#ffffff1f;border:1px solid #ffffff40;border-radius:24px;padding:36px 28px;max-width:420px;width:88%;text-align:center}}a{{display:inline-block;margin-top:16px;padding:12px 28px;border-radius:14px;background:#fff;color:#17352d;text-decoration:none;font-weight:bold}}</style></head><body><div class=\"card\"><div style=\"font-size:56px\">💳</div><h1 style=\"font-size:20px\">در حال انتقال به درگاه زرین‌پال...</h1><p>اگر به‌صورت خودکار منتقل نشدی، دکمه زیر را بزن.</p><a id=\"go\" href=\"{url}\" referrerpolicy=\"origin\">ورود به درگاه پرداخت</a></div><script>setTimeout(function(){{document.getElementById('go').click();}},600);</script></body></html>"""

SECURITY_HEADERS = {
    "Referrer-Policy": "origin",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


def _plain(message: str) -> str:
    for tag in ("<b>", "</b>", "<code>", "</code>"):
        message = message.replace(tag, "")
    return html.escape(" ".join(message.split()))


def _result_page(ok: bool, message: str) -> web.Response:
    page = PAGE.format(
        icon="✅" if ok else "❌",
        title="پرداخت موفق" if ok else "پرداخت ناموفق",
        message=_plain(message),
        bot=html.escape(BOT_USERNAME),
    )
    return web.Response(text=page, content_type="text/html", headers=SECURITY_HEADERS)


def create_app(bot: Bot) -> web.Application:
    async def zarinpal_callback(request: web.Request):
        # پارامترها طبق مستندات: Authority و Status (OK/NOK)؛ حروف کوچک هم پذیرفته می‌شود.
        query = {k.lower(): v for k, v in request.query.items()}
        authority = (query.get("authority") or "").strip()
        status = (query.get("status") or "").strip().upper()
        if not zarinpal.valid_authority(authority):
            return _result_page(False, "اطلاعات بازگشتی از درگاه نامعتبر است.")
        if status != "OK":
            # طبق مستندات در NOK نباید verify شود؛ وضعیت تراکنش تغییر نمی‌کند تا
            # اگر بانک دیرتر تایید کرد، worker آن را خودکار تایید کند.
            return _result_page(False, "پرداخت لغو شد یا ناموفق بود. اگر مبلغ کم شده، طی ۷۲ ساعت برمی‌گردد.")
        try:
            ok, message = await process_payment(bot, authority, notify_user=True)
        except Exception:  # noqa: BLE001
            log.exception("payment callback failed")
            ok, message = False, "خطای موقت در بررسی پرداخت. ربات چند دقیقه دیگر پرداخت را خودکار بررسی می‌کند."
        return _result_page(ok, message)

    async def start_pay(request: web.Request):
        authority = request.match_info.get("authority", "").strip()
        if not zarinpal.valid_authority(authority):
            return _result_page(False, "لینک پرداخت نامعتبر است.")
        payment = await db.get_payment(authority)
        if not payment:
            return _result_page(False, "تراکنش پیدا نشد یا منقضی شده. از داخل ربات فاکتور جدید بساز.")
        if payment["status"] == "paid":
            return _result_page(True, "این تراکنش قبلاً پرداخت و تایید شده است.")
        url = html.escape(zarinpal.gateway_url(authority, sandbox=await is_sandbox()), quote=True)
        return web.Response(text=REDIRECT_PAGE.format(url=url), content_type="text/html", headers=SECURITY_HEADERS)

    async def health(_: web.Request):
        return web.Response(text="SimPars bot is running ✅")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/zarinpal/callback", zarinpal_callback)
    app.router.add_get("/zarinpal/callback/", zarinpal_callback)
    # سازگاری با Callback قدیمی که ممکن است در تراکنش‌های باز ثبت شده باشد.
    app.router.add_get("/zibal/callback", zarinpal_callback)
    app.router.add_get("/pay/{authority}", start_pay)
    return app
