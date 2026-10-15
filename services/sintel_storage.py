"""Schema bootstrap for Sintel catalog and orders."""
from __future__ import annotations

import database as db


async def init_sintel_storage() -> None:
    """Create Sintel tables/settings without requiring a destructive migration."""
    await db._db.executescript("""
        CREATE TABLE IF NOT EXISTS sintel_services(
            service_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            rate TEXT NOT NULL DEFAULT '0',
            min_quantity INTEGER NOT NULL DEFAULT 0,
            max_quantity INTEGER NOT NULL DEFAULT 0,
            platform TEXT NOT NULL DEFAULT 'telegram',
            subcategory TEXT NOT NULL DEFAULT 'other',
            extra_data TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_sintel_services_platform
            ON sintel_services(platform, subcategory, is_active);
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
        CREATE INDEX IF NOT EXISTS idx_sintel_orders_user
            ON sintel_orders(user_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_sintel_orders_status
            ON sintel_orders(status);
    """)
    for key, value in (
        ("sintel_api", ""),
        ("sintel_enabled", "1"),
        ("sintel_profit_percent", ""),
        ("sintel_last_sync", ""),
    ):
        await db._db.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
            (key, value),
        )
    await db._db.commit()
