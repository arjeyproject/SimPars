"""SimPars - لایه دیتابیس SQLite."""
from __future__ import annotations

import os
import time

import aiosqlite

from config import DB_PATH

DEFAULT_SETTINGS = {"fivesim_api":"", "zibal_merchant":"", "zibal_sandbox":"0", "zibal_callback":"", "rate":"1200", "rate_source":"manual fallback", "rate_updated_at":"0", "pricing_paused":"0", "usd_rate_api_key":"", "usd_rate_url":"", "profit_percent":"30", "min_deposit":"10000", "max_deposit":"10000000", "force_join":"1", "force_join_channel":"", "maintenance":"0", "referral_percent":"5", "support_text":""}
SUCCESS_STATUSES = ("RECEIVED", "FINISHED")
SCHEMA_VERSION = "2"
_db: aiosqlite.Connection | None = None

# --- payments / invoices ------------------------------------------------------
# status:          new -> pending -> paid            (request_failed / canceled)
# delivery_status: awaiting -> processing -> delivered | failed | review | refunded
# (only for kind='purchase'; wallet top-ups keep delivery_status NULL)
_PAYMENT_COLUMNS = (
    ("kind", "TEXT NOT NULL DEFAULT 'wallet'"),
    ("invoice_id", "TEXT"),
    ("amount_rial", "INTEGER"),
    ("base_price", "INTEGER"),
    ("discount_percent", "INTEGER NOT NULL DEFAULT 0"),
    ("coupon", "TEXT"),
    ("context", "TEXT"),
    ("fingerprint", "TEXT"),
    ("delivery_status", "TEXT"),
    ("delivery_error", "TEXT"),
    ("delivery_attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("order_id", "INTEGER"),
    ("gateway_code", "INTEGER"),
    ("paid_at", "INTEGER"),
    ("updated_at", "INTEGER"),
)


async def _add_column(table: str, column: str, definition: str) -> None:
    try:
        await _db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except aiosqlite.OperationalError as exc:
        if "duplicate column" not in str(exc).lower():
            raise


async def _migrate_payments() -> None:
    """Additive, idempotent migration. Existing users/orders/payments are kept as-is."""
    for column, definition in _PAYMENT_COLUMNS:
        await _add_column("payments", column, definition)
    await _db.executescript("""
        CREATE TABLE IF NOT EXISTS payment_context(track_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
        CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status, kind, delivery_status);
        CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id, fingerprint);
    """)
    # Legacy direct purchases stored their payload in payment_context.
    await _db.execute("UPDATE payments SET kind='purchase', context=(SELECT payload FROM payment_context pc WHERE pc.track_id=payments.track_id) WHERE kind='wallet' AND track_id IN (SELECT track_id FROM payment_context)")
    # Paid legacy purchases were already delivered or refunded by the old code: never re-deliver them.
    await _db.execute("UPDATE payments SET delivery_status=CASE WHEN status='paid' THEN 'legacy' ELSE 'awaiting' END WHERE kind='purchase' AND delivery_status IS NULL")


async def init_db(path: str | None = None) -> None:
    global _db
    path = path or DB_PATH
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript("""
        CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, contact_phone TEXT, contact_updated_at INTEGER, balance INTEGER NOT NULL DEFAULT 0, is_banned INTEGER NOT NULL DEFAULT 0, referrer_id INTEGER, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, fivesim_id INTEGER, phone TEXT, product TEXT, country TEXT, operator TEXT, price INTEGER NOT NULL, status TEXT NOT NULL, code TEXT, sms_text TEXT, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, track_id TEXT UNIQUE, status TEXT NOT NULL DEFAULT 'pending', ref_number TEXT, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
        CREATE INDEX IF NOT EXISTS idx_users_ref ON users(referrer_id);
    """)
    for column, definition in (("contact_phone", "TEXT"), ("contact_updated_at", "INTEGER")):
        await _add_column("users", column, definition)
    await _migrate_payments()
    for key, value in DEFAULT_SETTINGS.items():
        await _db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value))
    await _db.execute("INSERT INTO settings(key, value) VALUES('schema_version', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (SCHEMA_VERSION,))
    await _db.commit()


async def close_db() -> None:
    if _db is not None:
        await _db.close()


async def _scalar(sql: str, params: tuple = ()) -> int:
    async with _db.execute(sql, params) as cur:
        row = await cur.fetchone()
    return 0 if not row or row[0] is None else int(row[0])


async def get_setting(key: str) -> str:
    async with _db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
    return (DEFAULT_SETTINGS.get(key, "") if row is None else row["value"]) or ""


async def get_int(key: str, default: int = 0) -> int:
    try:
        return int(float(await get_setting(key)))
    except ValueError:
        return default


async def get_float(key: str, default: float = 0.0) -> float:
    try:
        return float(await get_setting(key))
    except ValueError:
        return default


async def set_setting(key: str, value) -> None:
    await _db.execute("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    await _db.commit()


async def ensure_user(user_id: int, username: str | None, full_name: str | None) -> bool:
    cur = await _db.execute("INSERT OR IGNORE INTO users(user_id, username, full_name, created_at) VALUES(?, ?, ?, ?)", (user_id, username or "", full_name or "", int(time.time())))
    created = cur.rowcount == 1
    if not created:
        await _db.execute("UPDATE users SET username=?, full_name=? WHERE user_id=?", (username or "", full_name or "", user_id))
    await _db.commit()
    return created


async def get_user(user_id: int):
    async with _db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
        return await cur.fetchone()


async def set_contact_phone(user_id: int, phone: str) -> None:
    await _db.execute("UPDATE users SET contact_phone=?, contact_updated_at=? WHERE user_id=?", (phone, int(time.time()), user_id))
    await _db.commit()


async def has_contact_phone(user_id: int) -> bool:
    async with _db.execute("SELECT contact_phone FROM users WHERE user_id=?", (user_id,)) as cur:
        row = await cur.fetchone()
    return bool(row and row[0])


async def find_user(query: str):
    query = query.strip().lstrip("@")
    if query.isdigit():
        return await get_user(int(query))
    async with _db.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (query,)) as cur:
        return await cur.fetchone()


async def set_referrer(user_id: int, referrer_id: int) -> bool:
    cur = await _db.execute("UPDATE users SET referrer_id=? WHERE user_id=? AND referrer_id IS NULL", (referrer_id, user_id))
    await _db.commit()
    return cur.rowcount == 1


async def count_referrals(user_id: int) -> int:
    return await _scalar("SELECT COUNT(*) FROM users WHERE referrer_id=?", (user_id,))


async def add_balance(user_id: int, amount: int) -> None:
    await _db.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (int(amount), user_id))
    await _db.commit()


async def deduct_balance(user_id: int, amount: int) -> bool:
    cur = await _db.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (int(amount), user_id, int(amount)))
    await _db.commit()
    return cur.rowcount == 1


async def set_ban(user_id: int, banned: bool) -> None:
    await _db.execute("UPDATE users SET is_banned=? WHERE user_id=?", (1 if banned else 0, user_id))
    await _db.commit()


async def all_user_ids() -> list[int]:
    async with _db.execute("SELECT user_id FROM users WHERE is_banned=0") as cur:
        rows = await cur.fetchall()
    return [r[0] for r in rows]


async def user_stats(user_id: int) -> tuple[int, int]:
    marks = ",".join("?" * len(SUCCESS_STATUSES))
    count = await _scalar(f"SELECT COUNT(*) FROM orders WHERE user_id=? AND status IN ({marks})", (user_id, *SUCCESS_STATUSES))
    spent = await _scalar(f"SELECT SUM(price) FROM orders WHERE user_id=? AND status IN ({marks})", (user_id, *SUCCESS_STATUSES))
    return count, spent


async def create_order(user_id, fivesim_id, phone, product, country, operator, price, lifetime) -> int:
    now = int(time.time())
    cur = await _db.execute("INSERT INTO orders(user_id, fivesim_id, phone, product, country, operator, price, status, created_at, expires_at) VALUES(?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)", (user_id, fivesim_id, phone, product, country, operator, int(price), now, now + int(lifetime)))
    await _db.commit()
    return cur.lastrowid


async def get_order(order_id: int):
    async with _db.execute("SELECT * FROM orders WHERE id=?", (order_id,)) as cur:
        return await cur.fetchone()


async def user_orders(user_id: int, limit: int = 10):
    async with _db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)) as cur:
        return await cur.fetchall()


async def recent_orders(limit: int = 30):
    async with _db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (int(limit),)) as cur:
        return await cur.fetchall()


async def active_orders():
    async with _db.execute("SELECT * FROM orders WHERE status IN ('PENDING', 'RECEIVED') AND fivesim_id IS NOT NULL ORDER BY id") as cur:
        return await cur.fetchall()


async def set_order_sms(order_id: int, old_text: str, code: str, text: str) -> bool:
    cur = await _db.execute("UPDATE orders SET code=?, sms_text=?, status='RECEIVED' WHERE id=? AND COALESCE(sms_text, '')=? AND status IN ('PENDING', 'RECEIVED')", (code, text, order_id, old_text or ""))
    await _db.commit()
    return cur.rowcount == 1


async def transition_order(order_id: int, from_statuses: tuple, to_status: str) -> bool:
    marks = ",".join("?" * len(from_statuses))
    cur = await _db.execute(f"UPDATE orders SET status=? WHERE id=? AND status IN ({marks})", (to_status, order_id, *from_statuses))
    await _db.commit()
    return cur.rowcount == 1


async def create_payment(user_id: int, amount: int, track_id: str) -> None:
    """Legacy helper (kept for compatibility)."""
    await _db.execute("INSERT OR IGNORE INTO payments(user_id, amount, track_id, amount_rial, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?)", (user_id, int(amount), str(track_id), int(amount) * 10, int(time.time()), int(time.time())))
    await _db.commit()


async def get_payment(track_id: str):
    async with _db.execute("SELECT * FROM payments WHERE track_id=?", (str(track_id),)) as cur:
        return await cur.fetchone()


async def get_payment_by_invoice(invoice_id: str):
    async with _db.execute("SELECT * FROM payments WHERE invoice_id=?", (str(invoice_id),)) as cur:
        return await cur.fetchone()


async def create_invoice_row(user_id: int, kind: str, invoice_id: str, amount: int, amount_rial: int, base_price: int | None = None, discount_percent: int = 0, coupon: str = "", context: str | None = None, fingerprint: str | None = None) -> None:
    now = int(time.time())
    await _db.execute(
        "INSERT INTO payments(user_id, amount, track_id, status, kind, invoice_id, amount_rial, base_price, discount_percent, coupon, context, fingerprint, delivery_status, created_at, updated_at) VALUES(?, ?, NULL, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, int(amount), kind, invoice_id, int(amount_rial), base_price, int(discount_percent), coupon or "", context, fingerprint, "awaiting" if kind == "purchase" else None, now, now),
    )
    await _db.commit()


async def attach_authority(invoice_id: str, authority: str) -> bool:
    cur = await _db.execute("UPDATE payments SET track_id=?, status='pending', updated_at=? WHERE invoice_id=? AND status='new'", (str(authority), int(time.time()), invoice_id))
    await _db.commit()
    return cur.rowcount == 1


async def fail_invoice_request(invoice_id: str, error: str) -> None:
    await _db.execute("UPDATE payments SET status='request_failed', delivery_status=NULL, delivery_error=?, updated_at=? WHERE invoice_id=? AND status='new'", (str(error)[:500], int(time.time()), invoice_id))
    await _db.commit()


async def find_reusable_invoice(user_id: int, fingerprint: str, created_after: int):
    async with _db.execute("SELECT * FROM payments WHERE user_id=? AND fingerprint=? AND status='pending' AND track_id IS NOT NULL AND created_at>=? ORDER BY id DESC LIMIT 1", (user_id, fingerprint, int(created_after))) as cur:
        return await cur.fetchone()


async def mark_payment_paid(track_id: str, ref_number: str, gateway_code: int | None = None) -> bool:
    """Atomic pending/canceled -> paid. Exactly one caller can win."""
    now = int(time.time())
    cur = await _db.execute("UPDATE payments SET status='paid', ref_number=?, gateway_code=?, paid_at=?, updated_at=? WHERE track_id=? AND status IN ('pending', 'canceled')", (ref_number, gateway_code, now, now, str(track_id)))
    await _db.commit()
    return cur.rowcount == 1


async def mark_payment_canceled(track_id: str) -> bool:
    cur = await _db.execute("UPDATE payments SET status='canceled', updated_at=? WHERE track_id=? AND status='pending'", (int(time.time()), str(track_id)))
    await _db.commit()
    return cur.rowcount == 1


async def claim_delivery(track_id: str, from_statuses: tuple = ("awaiting",)) -> bool:
    """Atomic claim of a paid purchase for delivery; only one worker/callback gets True."""
    marks = ",".join("?" * len(from_statuses))
    cur = await _db.execute(f"UPDATE payments SET delivery_status='processing', delivery_attempts=delivery_attempts+1, updated_at=? WHERE track_id=? AND status='paid' AND kind='purchase' AND delivery_status IN ({marks})", (int(time.time()), str(track_id), *from_statuses))
    await _db.commit()
    return cur.rowcount == 1


async def finish_delivery(track_id: str, order_id: int) -> bool:
    cur = await _db.execute("UPDATE payments SET delivery_status='delivered', order_id=?, delivery_error=NULL, updated_at=? WHERE track_id=? AND delivery_status='processing'", (int(order_id), int(time.time()), str(track_id)))
    await _db.commit()
    return cur.rowcount == 1


async def fail_delivery(track_id: str, error: str, status: str = "failed") -> bool:
    cur = await _db.execute("UPDATE payments SET delivery_status=?, delivery_error=?, updated_at=? WHERE track_id=? AND delivery_status='processing'", (status, str(error)[:500], int(time.time()), str(track_id)))
    await _db.commit()
    return cur.rowcount == 1


async def refund_delivery_to_wallet(track_id: str) -> bool:
    """failed -> refunded and credit the paid amount once (single transaction)."""
    try:
        cur = await _db.execute("UPDATE payments SET delivery_status='refunded', updated_at=? WHERE track_id=? AND status='paid' AND delivery_status='failed'", (int(time.time()), str(track_id)))
        if cur.rowcount != 1:
            await _db.rollback()
            return False
        await _db.execute("UPDATE users SET balance=balance+(SELECT amount FROM payments WHERE track_id=?) WHERE user_id=(SELECT user_id FROM payments WHERE track_id=?)", (str(track_id), str(track_id)))
        await _db.commit()
        return True
    except Exception:
        await _db.rollback()
        raise


async def payments_to_reconcile(min_created: int, max_created: int, limit: int = 10):
    async with _db.execute("SELECT * FROM payments WHERE status IN ('pending', 'canceled') AND track_id IS NOT NULL AND created_at BETWEEN ? AND ? ORDER BY id DESC LIMIT ?", (int(min_created), int(max_created), int(limit))) as cur:
        return await cur.fetchall()


async def paid_awaiting_delivery(limit: int = 10):
    async with _db.execute("SELECT * FROM payments WHERE status='paid' AND kind='purchase' AND delivery_status='awaiting' ORDER BY id LIMIT ?", (int(limit),)) as cur:
        return await cur.fetchall()


async def stale_deliveries(updated_before: int, limit: int = 10):
    async with _db.execute("SELECT * FROM payments WHERE status='paid' AND kind='purchase' AND delivery_status='processing' AND COALESCE(updated_at, created_at)<? ORDER BY id LIMIT ?", (int(updated_before), int(limit))) as cur:
        return await cur.fetchall()


async def stats() -> dict:
    day_ago = int(time.time()) - 86400
    marks = ",".join("?" * len(SUCCESS_STATUSES))
    return {"users": await _scalar("SELECT COUNT(*) FROM users"), "new_users": await _scalar("SELECT COUNT(*) FROM users WHERE created_at>=?", (day_ago,)), "banned": await _scalar("SELECT COUNT(*) FROM users WHERE is_banned=1"), "orders": await _scalar("SELECT COUNT(*) FROM orders"), "success": await _scalar(f"SELECT COUNT(*) FROM orders WHERE status IN ({marks})", SUCCESS_STATUSES), "active": await _scalar("SELECT COUNT(*) FROM orders WHERE status='PENDING'"), "sales": await _scalar(f"SELECT SUM(price) FROM orders WHERE status IN ({marks})", SUCCESS_STATUSES), "sales_today": await _scalar(f"SELECT SUM(price) FROM orders WHERE status IN ({marks}) AND created_at>=?", (*SUCCESS_STATUSES, day_ago)), "deposits": await _scalar("SELECT SUM(amount) FROM payments WHERE status='paid' AND kind='wallet'"), "balances": await _scalar("SELECT SUM(balance) FROM users")}
