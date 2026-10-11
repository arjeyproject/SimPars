# اجرای SimPars با Docker

## پیش‌نیاز

روی Ubuntu نصب کن:

```bash
apt update && apt install -y docker.io docker-compose-plugin git
systemctl enable --now docker
```

## نصب و راه‌اندازی

```bash
git clone https://github.com/arjeyproject/SimPars.git /opt/SimPars
cd /opt/SimPars
cp .env.example .env
nano .env
```

حداقل `BOT_TOKEN` را در `.env` وارد کن. برای callback زرین‌پال، این مقدار را تنظیم کن:

```env
WEB_HOST=0.0.0.0
WEB_PORT=8080
BASE_URL=https://prostoreshop.site
```

سپس اجرا کن:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100 simpars
```

آدرس callback زرین‌پال:

```text
https://prostoreshop.site/zarinpal/callback
```

پورت `8080` باید از اینترنت قابل دسترسی باشد، یا Nginx باید درخواست مسیر `/zarinpal/callback` را به `127.0.0.1:8080` منتقل کند.

## فرمان‌های مدیریت

```bash
docker compose restart
docker compose logs -f --tail=100 simpars
docker compose down
docker compose up -d --build
```

دیتابیس در volume به نام `simpars-data` نگه‌داری می‌شود و با بازسازی کانتینر حذف نمی‌شود. برای بروزرسانی:

```bash
cd /opt/SimPars
git pull origin main
docker compose up -d --build
```

برای تست سلامت:

```bash
curl http://127.0.0.1:8080/
```

باید پاسخ `SimPars bot is running` دریافت کنی.
