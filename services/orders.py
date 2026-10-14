"""منطق پیگیری سفارش‌ها و بازگشت وجه."""
from __future__ import annotations
import logging, time
from aiogram import Bot
import database as db
import keyboards as kb
import texts
from services.fivesim import FiveSimClient, FiveSimError
from utils import esc, phone_ltr
log = logging.getLogger(__name__)
CLOSED_REMOTE = ("CANCELED", "TIMEOUT", "BANNED", "BAN", "EXPIRED")

def code_message(order, code: str, text: str) -> str:
    return texts.CODE_RECEIVED.format(order_id=order["id"], phone=phone_ltr(order["phone"]), code=esc(code or "—"), text=esc(text or "—"))

async def refund(bot: Bot, order, to_status: str, reason: str, notify: bool = True) -> bool:
    if not await db.transition_order(order["id"], ("PENDING",), to_status): return False
    await db.add_balance(order["user_id"], order["price"])
    if notify:
        try: await bot.send_message(order["user_id"], texts.REFUNDED.format(order_id=order["id"], phone=phone_ltr(order["phone"]), price=order["price"], reason=reason), reply_markup=kb.back_main())
        except Exception as exc: log.warning("refund notify failed: %s", exc)
    return True

def _latest_sms(payload) -> tuple[str, str] | None:
    if not isinstance(payload, list): return None
    for item in reversed(payload):
        if isinstance(item, dict):
            code, text = str(item.get("code") or "").strip(), str(item.get("text") or "").strip()
            if code or text: return code, text
    return None

def _is_closed_error(exc: Exception) -> bool:
    value = str(exc).lower()
    return any(token in value for token in ("banned", "ban", "canceled", "cancelled", "timeout", "expired", "order not found", "order_not_found"))

async def sync_order(bot: Bot, order, notify: bool = True) -> dict:
    client = FiveSimClient(await db.get_setting("fivesim_api"))
    try: data = await client.check(order["fivesim_id"])
    except FiveSimError as exc:
        if order["status"] == "PENDING" and _is_closed_error(exc):
            banned = "ban" in str(exc).lower(); refunded = await refund(bot, order, "TIMEOUT", texts.REASON_BANNED if banned else texts.REASON_TIMEOUT, notify)
            return {"status": "TIMEOUT", "new": refunded, "reason": "banned" if banned else "timeout", "code": order["code"], "text": order["sms_text"]}
        raise
    if not isinstance(data, dict): raise FiveSimError("invalid provider response")
    remote = str(data.get("status") or "").upper(); result = {"status": order["status"], "new": False, "reason": "", "code": order["code"], "text": order["sms_text"]}
    if order["status"] == "PENDING" and remote in CLOSED_REMOTE:
        banned = remote in ("BANNED", "BAN"); refunded = await refund(bot, order, "TIMEOUT", texts.REASON_BANNED if banned else texts.REASON_TIMEOUT, notify)
        result.update(status="TIMEOUT", new=refunded, reason="banned" if banned else "timeout"); return result
    latest = _latest_sms(data.get("sms"))
    if latest:
        code, text = latest; result.update(status="RECEIVED", code=code, text=text)
        changed = text != (order["sms_text"] or "") or code != (order["code"] or "")
        if changed and await db.set_order_sms(order["id"], order["sms_text"] or "", code, text):
            result["new"] = True
            if notify:
                try: await bot.send_message(order["user_id"], code_message(order, code, text), reply_markup=kb.order_received_kb(order["id"]))
                except Exception as exc: log.warning("code notify failed: %s", exc)
    now = time.time()
    if result["status"] == "PENDING" and now > order["expires_at"]:
        try: await client.cancel(order["fivesim_id"])
        except FiveSimError as exc:
            if "sms" in str(exc).lower(): return result
        await refund(bot, order, "TIMEOUT", texts.REASON_TIMEOUT, notify); result.update(status="TIMEOUT", reason="timeout")
    elif result["status"] == "RECEIVED" and (now > order["expires_at"] or remote == "FINISHED"):
        if remote != "FINISHED":
            try: await client.finish(order["fivesim_id"])
            except FiveSimError: log.warning("could not finish remote order %s", order["fivesim_id"])
        await db.transition_order(order["id"], ("PENDING", "RECEIVED"), "FINISHED"); result["status"] = "FINISHED"
    return result
