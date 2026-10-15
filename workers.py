"""Background workers for payments, 5Sim and Sintel orders."""
from __future__ import annotations
import asyncio
import logging
from aiogram import Bot
import database as db
from config import CHECK_INTERVAL, MARKET_INTERVAL
from services.fivesim import FiveSimError
from services.market import refresh_rate
from services.orders import sync_order
from services.payments import reconcile_pending_payments
from services.sintel_orders import sync_all_pending_orders

log = logging.getLogger(__name__)
RECONCILE_INTERVAL = 60
SINTEL_INTERVAL = 60

async def order_worker(bot: Bot) -> None:
    log.info("background workers started")
    market_tick = reconcile_tick = sintel_tick = 0
    while True:
        try:
            if market_tick <= 0:
                ok, detail = await refresh_rate()
                if not ok: log.warning("market refresh skipped: %s", detail)
                market_tick = max(1, MARKET_INTERVAL // CHECK_INTERVAL)
            market_tick -= 1
            if reconcile_tick <= 0:
                try: await reconcile_pending_payments(bot)
                except Exception: log.exception("payment reconcile failed")
                reconcile_tick = max(1, RECONCILE_INTERVAL // CHECK_INTERVAL)
            reconcile_tick -= 1
            if sintel_tick <= 0 and await db.get_setting("sintel_enabled") == "1" and await db.get_setting("sintel_api"):
                try: await sync_all_pending_orders(bot)
                except Exception: log.exception("Sintel order sync failed")
                sintel_tick = max(1, SINTEL_INTERVAL // CHECK_INTERVAL)
            sintel_tick -= 1
            if await db.get_setting("fivesim_api"):
                for order in await db.active_orders():
                    try: await sync_order(bot, order, notify=True)
                    except FiveSimError as exc: log.warning("sync order %s: %s", order["id"], exc)
                    except Exception: log.exception("sync order %s failed", order["id"])
                    await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            raise
        except Exception: log.exception("background worker loop error")
        await asyncio.sleep(CHECK_INTERVAL)
