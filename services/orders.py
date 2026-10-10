"""SimPars - منطق پیگیری سفارش‌ها و بازگشت وجه"""
from __future__ import annotations

import logging
import time

from aiogram import Bot

import database as db
import keyboards as kb
import texts
from services.fivesim import FiveSimClient, FiveSimError
from utils import esc

log = logging.getLogger(__name__)
CLOSED_REMOTE = ("CANCELED", "TIMEOUT", "BANNED")


def code_message(order, code: str, text: str) -> str:
    return texts.CODE_RECEIVED.format(
        order_id=order["id"], phone=esc(order["phone"]),
        code=esc(code or "—"), text=esc(text or "—"),
    )


async def refund(bot: Bot, order, to_status: str, reason: str, notify: bool = True) -> bool:
    """بازگشت وجه فقط یک‌بار انجام می‌شود (تغییر وضعیت اتمیک)."""
    if not await db.transition_order(order["id"], ("PENDING",), to_status):
        return False
    await db.add_balance(order["user_id"], order["price"])
    if notify:
        try:
            await bot.send_message(
                order["user_id"],
                texts.REFUNDED.format(order_id=order["id"], phone=esc(order["phone"]),
                                      price=order["price"], reason=reason),
                reply_markup=kb.back_main(),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("refund notify failed: %s", exc)
    return True


async def sync_order(bot: Bot, order, notify: bool = True) -> dict:
    """وضعیت سفارش را از 5Sim می‌گیرد و دیتابیس را بروز می‌کند.

    خروجی: {"status": ..., "new": bool, "code": str|None, "text": str|None}
    """
    client = FiveSimClient(await db.get_setting("fivesim_api"))
    data = await client.check(order["fivesim_id"])
    remote = str(data.get("status") or "").upper()
    sms_list = data.get("sms") or []
    result = {"status": order["status"], "new": False, "code": order["code"], "text": order["sms_text"]}

    if sms_list:
        last = sms_list[-1] if isinstance(sms_list[-1], dict) else {}
        code = str(last.get("code") or "").strip()
        text = str(last.get("text") or "").strip()
        result.update(status="RECEIVED", code=code, text=text)
        changed = text != (order["sms_text"] or "") or code != (order["code"] or "")
        if changed and await db.set_order_sms(order["id"], order["sms_text"] or "", code, text):
            result["new"] = True
            if notify:
                try:
                    await bot.send_message(order["user_id"], code_message(order, code, text),
                                           reply_markup=kb.order_received_kb(order["id"]))
                except Exception as exc:  # noqa: BLE001
                    log.warning("code notify failed: %s", exc)

    now = time.time()
    if result["status"] == "PENDING":
        if remote in CLOSED_REMOTE:
            await refund(bot, order, "TIMEOUT", texts.REASON_TIMEOUT, notify)
            result["status"] = "TIMEOUT"
        elif now > order["expires_at"]:
            try:
                await client.cancel(order["fivesim_id"])
            except FiveSimError as exc:
                if "sms" in str(exc).lower():
                    return result  # پیامک رسیده؛ در دور بعد ثبت می‌شود
            await refund(bot, order, "TIMEOUT", texts.REASON_TIMEOUT, notify)
            result["status"] = "TIMEOUT"
    elif result["status"] == "RECEIVED":
        if now > order["expires_at"] or remote in ("FINISHED", *CLOSED_REMOTE):
            if remote not in ("FINISHED", *CLOSED_REMOTE):
                try:
                    await client.finish(order["fivesim_id"])
                except FiveSimError:
                    pass
            await db.transition_order(order["id"], ("PENDING", "RECEIVED"), "FINISHED")
            result["status"] = "FINISHED"
    return result
