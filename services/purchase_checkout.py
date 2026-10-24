"""Direct payment context and idempotent 5SIM checkout."""
from __future__ import annotations
import json, logging, time
from aiogram import Bot
import database as db
import texts
from config import ORDER_LIFETIME
from services import availability, coupons, fivesim, zarinpal
from services.fivesim import FiveSimClient, FiveSimError, PurchaseUnknownError
from utils import calc_price, country_title, esc, phone_ltr, service_title
log=logging.getLogger(__name__); _table_ready=False

async def _ensure_context_table()->None:
    global _table_ready
    if _table_ready:return
    await db._db.execute("CREATE TABLE IF NOT EXISTS payment_context(track_id TEXT PRIMARY KEY,payload TEXT NOT NULL)")
    await db._db.commit(); _table_ready=True

async def get_context(track_id:str):
    await _ensure_context_table()
    async with db._db.execute("SELECT payload FROM payment_context WHERE track_id=?",(str(track_id),)) as cur: row=await cur.fetchone()
    if not row:return None
    try:return json.loads(row[0])
    except json.JSONDecodeError:return None

async def _pricing()->tuple[float,float]:return await db.get_float("rate",1000),max(0.0,await db.get_float("profit_percent",30))

async def resolve(payload:dict)->tuple[int,str,str]:
    # availability.country_options tolerates key casing/spacing and falls back
    # through cache -> fresh fetch -> full catalog, so a stocked country is
    # never mistaken for "no free phones".
    values=await availability.country_options(payload["product"],payload["country"])
    if not values:raise FiveSimError("no free phones")
    selected=str(payload.get("operator") or "").strip()
    match=next((item for item in values if item[0].lower()==selected.lower()),None)
    if not match: match=fivesim.choose_operator(values,payload["country"],payload["product"])
    if not match:raise FiveSimError("no free phones")
    operator,cost,_=match; rate,profit=await _pricing(); base=calc_price(cost,rate,profit); percent=0; code=(payload.get("coupon") or "").strip().upper()
    if code:
        valid,_,percent=await coupons.validate(code)
        if not valid:code,percent="",0
    return max(1,int(round(base*(100-percent)/100))),operator,code

async def create_invoice(user_id:int,payload:dict)->tuple[str,int]:
    from services.payments import get_callback_url,get_merchant
    price,operator,code=await resolve(payload); merchant=await get_merchant()
    if not merchant:raise zarinpal.ZarinpalError("درگاه زرین‌پال تنطیم نشده است")
    user=await db.get_user(user_id); mobile=user["contact_phone"] if user and "contact_phone" in user.keys() else None
    authority=await zarinpal.create_payment(merchant,price*10,await get_callback_url(),description=f"خرید شماره {payload['product']} - کاربر {user_id}",order_id=f"buy-{user_id}-{int(time.time())}",mobile=mobile)
    stored={**payload,"operator":operator,"coupon":code,"price":price}; await _ensure_context_table()
    await db._db.execute("INSERT OR REPLACE INTO payment_context(track_id,payload) VALUES(?,?)",(authority,json.dumps(stored,ensure_ascii=False))); await db._db.commit()
    await db.create_payment(user_id,price,authority); return authority,price

async def reserve_order(user_id:int,payload:dict,price:int,*,wallet:bool)->tuple[int,bool]:
    """Create one local pending reservation before provider I/O. The row is the retry/idempotency key."""
    now=int(time.time()); product=str(payload["product"]); country=str(payload["country"]); operator=str(payload.get("operator") or "")
    await db._db.execute("BEGIN IMMEDIATE")
    try:
        async with db._db.execute("SELECT id,status FROM orders WHERE user_id=? AND product=? AND country=? AND operator=? AND status='PENDING' AND fivesim_id IS NULL AND created_at>=? ORDER BY id DESC LIMIT 1",(user_id,product,country,operator,now-900)) as cur: existing=await cur.fetchone()
        if existing:
            await db._db.rollback(); return int(existing["id"]),False
        if wallet:
            cur=await db._db.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",(int(price),user_id,int(price)))
            if cur.rowcount!=1: await db._db.rollback(); return 0,False
        cur=await db._db.execute("INSERT INTO orders(user_id,fivesim_id,phone,product,country,operator,price,status,created_at,expires_at) VALUES(?,NULL,'',?,?,?,?, 'PENDING',?,?)",(user_id,product,country,operator,int(price),now,now+ORDER_LIFETIME))
        order_id=int(cur.lastrowid); await db._db.commit(); return order_id,True
    except Exception:
        await db._db.rollback(); raise

async def complete_reserved_order(order_id:int,data:dict,operator:str)->bool:
    cur=await db._db.execute("UPDATE orders SET fivesim_id=?,phone=?,operator=? WHERE id=? AND status='PENDING' AND fivesim_id IS NULL",(int(data["id"]),str(data.get("phone") or ""),str(data.get("operator") or operator),int(order_id)))
    await db._db.commit(); return cur.rowcount==1

async def refund_reserved_order(order_id:int)->bool:
    await db._db.execute("BEGIN IMMEDIATE")
    try:
        async with db._db.execute("SELECT user_id,price FROM orders WHERE id=? AND status='PENDING' AND fivesim_id IS NULL",(int(order_id),)) as cur: row=await cur.fetchone()
        if not row: await db._db.rollback(); return False
        cur=await db._db.execute("UPDATE orders SET status='CANCELED' WHERE id=? AND status='PENDING' AND fivesim_id IS NULL",(int(order_id),))
        if cur.rowcount!=1: await db._db.rollback(); return False
        await db._db.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(int(row["price"]),int(row["user_id"])))
        await db._db.commit(); return True
    except Exception:
        await db._db.rollback(); raise

async def finish_paid_purchase(bot:Bot,payment,payload:dict,ref:str)->tuple[bool,str,int|None]:
    user_id=int(payment["user_id"]); paid=int(payment["amount"]); refund_note=f"مبلغ <b>{paid:,} تومان</b> به کیف پولت برگشت خورد."
    coupon_code=(payload.get("coupon") or "").strip().upper()
    try: _,operator,_=await resolve({**payload,"coupon":""})
    except Exception as exc:
        log.warning("paid purchase resolve failed: %s",exc)
        # Payment is already verified at this point. If inventory disappeared
        # before order reservation, credit the exact paid amount back instead
        # of only telling the buyer that a refund happened.
        try: await db.add_balance(user_id,paid)
        except Exception:
            log.exception("paid purchase refund failed: user=%s amount=%s",user_id,paid)
            return False,"پرداخت تأیید شد اما موجودی شماره مشخص نشد و بازگشت مبلغ نیازمند بررسی پشتیبانی است؛ لطفاً خرید را دوباره انجام نده.",None
        return False,f"پرداخت تأیید شد اما این شماره موجود نیست.{chr(10)}{refund_note}",None
    payload={**payload,"operator":operator}; order_id,created=await reserve_order(user_id,payload,paid,wallet=False)
    if not created:return False,"این پرداخت در حال بررسی است؛ خرید دوباره انجام نده.",order_id
    token=await db.get_setting("fivesim_api")
    if not token: await refund_reserved_order(order_id); return False,f"پرداخت تأیید شد اما فروشگاه موقتاً در دسترس نیست.{chr(10)}{refund_note}",None
    try:data=await FiveSimClient(token).buy(payload["country"],operator,payload["product"])
    except PurchaseUnknownError:
        log.error("ambiguous paid purchase: user=%s order=%s",user_id,order_id); return False,"پرداخت تأیید شد اما پاسخ سرویس نامشخص است؛ خرید دوباره انجام نده.",order_id
    except FiveSimError as exc:
        await refund_reserved_order(order_id); log.warning("paid purchase failed: %s",exc); return False,f"پرداخت تأیید شد اما سفارش انجام نشد.{chr(10)}{refund_note}",None
    if not await complete_reserved_order(order_id,data,operator): return False,"پرداخت تأیید شد اما ثبت سفارش نیازمند بررسی است؛ خرید دوباره انجام نده.",order_id
    if coupon_code:
        try: await coupons.consume(coupon_code)
        except Exception: log.warning("coupon consume failed")
    phone=str(data.get("phone") or ""); countries=await fivesim.countries_safe(); message=texts.ORDER_CREATED.format(order_id=order_id,service=service_title(payload["product"]),country=country_title(payload["country"],countries),phone=phone_ltr(phone),price=paid,minutes=ORDER_LIFETIME//60)
    return True,message,order_id
