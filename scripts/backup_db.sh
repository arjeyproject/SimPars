#!/usr/bin/env bash
# بکاپ امن دیتابیس SimPars از داخل کانتینر (بدون توقف ربات).
# نصب در cron (هر شب ساعت ۴):
#   0 4 * * * /root/SimPars/scripts/backup_db.sh >> /var/log/simpars-backup.log 2>&1
set -euo pipefail
BACKUP_DIR="${BACKUP_DIR:-/root/simpars-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
docker exec simpars python -c "import sqlite3; s=sqlite3.connect('/app/data/simpars.db'); d=sqlite3.connect('/app/data/backup.db'); s.backup(d); d.close(); s.close()"
docker cp simpars:/app/data/backup.db "$BACKUP_DIR/simpars-$STAMP.db"
docker exec simpars rm -f /app/data/backup.db
find "$BACKUP_DIR" -name 'simpars-*.db' -mtime +"$KEEP_DAYS" -delete
echo "backup ok: $BACKUP_DIR/simpars-$STAMP.db"
