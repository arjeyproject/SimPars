"""SimPars Bot - @SimParsBot"""
from __future__ import annotations
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiohttp import web
import config
import database as db
from handlers import admin, buy, fallback, user, wallet, market_admin
from middlewares import AccessMiddleware
from webserver import create_app
from workers import order_worker

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    log = logging.getLogger("simpars")
    if not config.BOT_TOKEN:
        log.error("BOT_TOKEN خالی است! فایل .env را تکمیل کنید."); sys.exit(1)
    await db.init_db()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    dp = Dispatcher(storage=MemoryStorage())
    access = AccessMiddleware(); dp.message.outer_middleware(access); dp.callback_query.outer_middleware(access)
    dp.include_routers(admin.router, market_admin.router, user.router, buy.router, wallet.router, fallback.router)
    await bot.set_my_commands([BotCommand(command="start", description="🏠 منوی اصلی"), BotCommand(command="admin", description="⚙️ پنل مدیریت (فقط ادمین)")])
    runner = web.AppRunner(create_app(bot)); await runner.setup()
    try:
        await web.TCPSite(runner, config.WEB_HOST, config.WEB_PORT).start(); log.info("web server on %s:%s", config.WEB_HOST, config.WEB_PORT)
    except OSError as exc: log.warning("web server not started (%s)", exc)
    worker = asyncio.create_task(order_worker(bot)); me = await bot.get_me(); log.info("🚀 @%s is running...", me.username)
    try:
        await bot.delete_webhook(drop_pending_updates=True); await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        worker.cancel(); await runner.cleanup(); await db.close_db(); await bot.session.close()

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): pass
