"""SimPars - بررسی خودکار سفارش‌ها در پس‌زمینه"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

import database as db
from config import CHECK_INTERVAL
from services.fivesim import FiveSimError
from services.orders import sync_order

log = logging.getLogger(__name__)


async def order_worker(bot: Bot) -> None:
    log.info("order worker started")
    while True:
        try:
            if await db.get_setting("fivesim_api"):
                for order in await db.active_orders():
                    try:
                        await sync_order(bot, order, notify=True)
                    except FiveSimError as exc:
                        log.warning("sync order %s: %s", order["id"], exc)
                    except Exception:  # noqa: BLE001
                        log.exception("sync order %s failed", order["id"])
                    await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("order worker loop error")
        await asyncio.sleep(CHECK_INTERVAL)
