#!/usr/bin/env bash
# ==========================================
#   SimPars Bot - نصب خودکار روی اوبونتو
# ==========================================
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE=/etc/systemd/system/simpars.service

if [ "$EUID" -ne 0 ]; then
  echo "❌ لطفاً با دسترسی root اجرا کنید:  sudo bash install.sh"
  exit 1
fi

echo "🚀 در حال نصب پیش‌نیازها..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git

cd "$APP_DIR"
echo "📦 در حال ساخت محیط پایتون و نصب کتابخانه‌ها..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
fi

if ! grep -q "^BOT_TOKEN=..*" .env; then
  read -rp "🤖 توکن ربات (از BotFather) را وارد کنید: " TOKEN
  if [ -n "$TOKEN" ]; then
    sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=$TOKEN|" .env
  fi
fi

echo "⚙️ در حال ساخت سرویس همیشه روشن..."
cat > "$SERVICE" <<UNIT
[Unit]
Description=SimPars Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

if command -v ufw >/dev/null 2>&1; then
  ufw allow 8080/tcp >/dev/null 2>&1 || true
fi

systemctl daemon-reload
systemctl enable simpars >/dev/null 2>&1
systemctl restart simpars
sleep 3

echo ""
echo "✅ نصب تمام شد!"
echo "📊 وضعیت ربات:   systemctl status simpars"
echo "📜 مشاهده لاگ:   journalctl -u simpars -f"
echo "🔁 ریستارت:      systemctl restart simpars"
echo ""
echo "👉 حالا در تلگرام به @SimParsBot برو و /admin رو بزن."
