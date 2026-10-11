"""SimPars - وب‌سرور برای Callback زرین‌پال."""
from __future__ import annotations
import html
from aiogram import Bot
from aiohttp import web
from services.payments import process_payment
from config import BOT_USERNAME
PAGE = """<!doctype html><html lang=\"fa\" dir=\"rtl\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>SimPars | نتیجه پرداخت</title><style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:Tahoma,sans-serif;background:linear-gradient(135deg,#123d31,#4e9279);color:#fff}}.card{{background:#ffffff1f;border:1px solid #ffffff40;border-radius:24px;padding:36px 28px;max-width:420px;width:88%;text-align:center;box-shadow:0 10px 40px #0005}}.icon{{font-size:64px}}h1{{font-size:22px}}p{{line-height:1.9;opacity:.9}}a{{display:inline-block;margin-top:16px;padding:12px 28px;border-radius:14px;background:#fff;color:#17352d;text-decoration:none;font-weight:bold}}</style></head><body><div class=\"card\"><div class=\"icon\">{icon}</div><h1>{title}</h1><p>{message}</p><a href=\"https://t.me/{bot}\">🤖 بازگشت به ربات</a></div></body></html>"""
def _plain(message: str) -> str:
    for tag in ("<b>", "</b>", "<code>", "</code>"): message = message.replace(tag, "")
    return html.escape(" ".join(message.split()))
def create_app(bot: Bot) -> web.Application:
    async def zarinpal_callback(request: web.Request):
        authority = request.query.get("Authority", "")
        status = request.query.get("Status", "")
        if not authority or status.upper() != "OK": ok, message = False, "پرداخت لغو شد یا ناموفق بود."
        else: ok, message = await process_payment(bot, authority, notify_user=True)
        page = PAGE.format(icon="✅" if ok else "❌", title="پرداخت موفق" if ok else "پرداخت ناموفق", message=_plain(message), bot=BOT_USERNAME)
        return web.Response(text=page, content_type="text/html")
    async def health(_: web.Request): return web.Response(text="SimPars bot is running ✅")
    app = web.Application(); app.router.add_get("/", health); app.router.add_get("/zarinpal/callback", zarinpal_callback); return app
