#!/usr/bin/env python3
"""Read-only production preflight for SimPars."""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def env(path: Path) -> dict[str, str]:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); out[k] = v.strip().strip('"').strip("'")
    return out

def check(label: str, ok: bool, detail: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {detail}")
    return ok

def main() -> int:
    e = env(ROOT / ".env")
    results = [check(".env", bool(e), "loaded" if e else "missing"), check("BOT_TOKEN", bool(e.get("BOT_TOKEN")), "configured" if e.get("BOT_TOKEN") else "missing"), check("ADMIN_IDS", bool(e.get("ADMIN_IDS")), "configured" if e.get("ADMIN_IDS") else "missing")]
    db_path = Path(e.get("DB_PATH", "data/simpars.db")); db_path = db_path if db_path.is_absolute() else ROOT / db_path
    results.append(check("database", db_path.exists(), str(db_path) if db_path.exists() else "not initialized"))
    if db_path.exists():
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"users", "orders", "payments", "settings"}
            results.append(check("database schema", required <= tables, "required tables present" if required <= tables else f"missing {sorted(required - tables)}"))
            settings = {r[0]: r[1] for r in con.execute("SELECT key,value FROM settings")}
            results.append(check("5Sim API", bool(settings.get("fivesim_api")), "configured in admin" if settings.get("fivesim_api") else "add it from /admin"))
            gateway = bool(settings.get("zibal_merchant")) or settings.get("zibal_sandbox") == "1"
            results.append(check("payment gateway", gateway, "configured" if gateway else "configure Zibal in /admin"))
            try: pricing = float(settings.get("rate", "0")) > 0 and float(settings.get("profit_percent", "-1")) >= 0
            except ValueError: pricing = False
            results.append(check("pricing", pricing, "rate and profit look valid" if pricing else "invalid rate/profit"))
            con.close()
        except Exception as exc: results.append(check("database read", False, str(exc)))
    print("\nRead-only check complete. Run a small sandbox payment and one low-cost 5Sim order before opening sales.")
    return 0 if all(results) else 1

if __name__ == "__main__": sys.exit(main())
