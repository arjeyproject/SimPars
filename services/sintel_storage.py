"""Non-destructive storage bootstrap for the Panelix catalog and orders."""
from __future__ import annotations
import database as db


async def _add_column(table: str, column: str, definition: str) -> None:
    try:
        await db._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except Exception as exc:
        if "duplicate column" not in str(exc).lower():
            raise


async def init_sintel_storage() -> None:
    # The table names are retained so existing orders and payments remain intact.
    await db._db.executescript("""
        CREATE TABLE IF NOT EXISTS sintel_services(
            service_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            rate TEXT NOT NULL DEFAULT '0',
            min_quantity INTEGER NOT NULL DEFAULT 0,
            max_quantity INTEGER NOT NULL DEFAULT 0,
            platform TEXT NOT NULL DEFAULT 'other',
            subcategory TEXT NOT NULL DEFAULT 'other',
            extra_data TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_sintel_services_platform ON sintel_services(platform, subcategory, is_active);
        CREATE TABLE IF NOT EXISTS sintel_orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider_order_id TEXT NOT NULL,
            service_id INTEGER NOT NULL,
            link TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            provider_cost INTEGER NOT NULL DEFAULT 0,
            selling_price INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'PENDING',
            remains INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sintel_orders_user ON sintel_orders(user_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_sintel_orders_status ON sintel_orders(status);
        CREATE TABLE IF NOT EXISTS panelix_sync_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT, started_at INTEGER NOT NULL, finished_at INTEGER,
            success INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
            new_count INTEGER NOT NULL DEFAULT 0, updated_count INTEGER NOT NULL DEFAULT 0,
            unavailable_count INTEGER NOT NULL DEFAULT 0, error_count INTEGER NOT NULL DEFAULT 0,
            detail TEXT NOT NULL DEFAULT ''
        );
    """)
    for column, definition in (
        ("provider", "TEXT NOT NULL DEFAULT 'panelix'"), ("currency", "TEXT NOT NULL DEFAULT ''"),
        ("rate_unit", "TEXT NOT NULL DEFAULT ''"), ("price_verified", "INTEGER NOT NULL DEFAULT 0"),
        ("provider_category", "TEXT NOT NULL DEFAULT ''"), ("provider_type", "TEXT NOT NULL DEFAULT ''"),
        ("description", "TEXT NOT NULL DEFAULT ''"), ("display_name", "TEXT NOT NULL DEFAULT ''"),
        ("profit_percent", "TEXT NOT NULL DEFAULT ''"), ("retail_price", "INTEGER NOT NULL DEFAULT 0"),
        ("display_order", "INTEGER NOT NULL DEFAULT 0"), ("last_seen_at", "INTEGER NOT NULL DEFAULT 0"),
        ("unavailable_reason", "TEXT NOT NULL DEFAULT ''"),
    ):
        await _add_column("sintel_services", column, definition)
    for column, definition in (("provider", "TEXT NOT NULL DEFAULT 'panelix'"), ("refill_id", "TEXT"), ("refund_applied", "INTEGER NOT NULL DEFAULT 0")):
        await _add_column("sintel_orders", column, definition)
    for key, value in (
        ("panelix_api", ""), ("panelix_enabled", "1"), ("panelix_last_sync", ""),
        ("panelix_last_sync_result", ""), ("panelix_sync_interval", "86400"),
        ("panelix_rate_unit", "unverified"), ("panelix_currency", "unverified"),
        ("panelix_profit_percent", ""), ("sintel_api", ""), ("sintel_enabled", "0"),
        ("sintel_profit_percent", ""), ("sintel_last_sync", ""),
    ):
        await db._db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value))
    await db._db.commit()
