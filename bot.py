"""SimPars Bot - @SimParsBot"""
from __future__ import annotations
import asyncio, logging, sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiohttp import web
import config
import database as db
from handlers import admin, buy, catalog, channel, fallback, recent_users, reports, user, wallet, market_admin
from middlewares import AccessMiddleware
from webserver import create_app
from workers import order_worker


def apply_gateway_branding() -> None:
    import texts, keyboards as kb
    for name in ("WELCOME", "PAYMENT_CREATED", "ADMIN_HOME", "ADMIN_ZIBAL"):
        if hasattr(texts, name): setattr(texts, name, getattr(texts, name).replace("زیبال", "زرین‌پال").replace("zibal.ir", "zarinpal.com"))
    title, kind, back, hint = admin.SETTINGS.get("zibal_merchant", ("", "secret", "panel_zibal", ""))
    admin.SETTINGS["zibal_merchant"] = ("💳 مرچنت زرین‌پال", kind, back, "مرچنت آیدی ۳۶ کاراکتری را از پنل زرین‌پال کپی کن و بفرست.")
    admin.SETTINGS["zibal_callback"] = ("🌐 آدرس بازگشت زرین‌پال", "url", "panel_zibal", "آدرس کامل callback را بفرست. مثال:\n<code>https://prostoreshop.site/zarinpal/callback</code>")
    original_menu, original_gateway = kb.admin_menu, kb.zibal_admin_kb
    def admin_menu(force_join, maintenance):
        result = original_menu(force_join, maintenance)
        result.inline_keyboard.insert(-1, [kb.btn("👥 کاربران اخیر", "adm_recent_users", style="primary")])
        for row in result.inline_keyboard:
            for button in row:
                button.text = button.text.replace("درگاه زیبال", "درگاه زرین‌پال")
        return result
    def gateway_menu(sandbox, has_merchant):
        result = original_gateway(sandbox, has_merchant)
        for row in result.inline_keyboard:
            for button in row:
                button.text = button.text.replace("زیبال", "زرین‌پال").replace("zibal.ir", "zarinpal.com")
                if button.url and "zibal.ir" in button.url: button.url = "https://www.zarinpal.com"
        return result
    kb.admin_menu, kb.zibal_admin_kb = admin_menu, gateway_menu


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    log = logging.getLogger("simpars")
    if not config.BOT_TOKEN: log.error("BOT_TOKEN خالی است! فایل .env را تکمیل کنید."); sys.exit(1)
    await db.init_db(); apply_gateway_branding()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    dp = Dispatcher(storage=MemoryStorage()); access = AccessMiddleware(); dp.message.outer_middleware(access); dp.callback_query.outer_middleware(access)
    dp.include_routers(admin.router, recent_users.router, channel.router, market_admin.router, reports.router, catalog.router, buy.router, user.router, wallet.router, fallback.router)
    await bot.set_my_commands([BotCommand(command="start", description="🏠 منوی اصلی"), BotCommand(command="admin", description="⚙️ پنل مدیریت (فقط ادمین)"), BotCommand(command="sales", description="📊 گزارش فروش (فقط ادمین)")])
    runner = web.AppRunner(create_app(bot)); await runner.setup()
    try: await web.TCPSite(runner, config.WEB_HOST, config.WEB_PORT).start(); log.info("web server on %s:%s", config.WEB_HOST, config.WEB_PORT)
    except OSError as exc: log.warning("web server not started (%s)", exc)
    worker = asyncio.create_task(order_worker(bot)); me = await bot.get_me(); log.info("🚀 @%s is running...", me.username)
    try:
        await bot.delete_webhook(drop_pending_updates=True); await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        worker.cancel(); await runner.cleanup(); await db.close_db(); await bot.session.close()


if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): pass
