# نصب SimPars با زرین‌پال

```bash
cd /root/SimPars
git pull origin main
sudo systemctl restart simpars
```

## ۱) تنظیمات درست (همه باید روی یک دامنه باشند)

| مورد | مقدار |
|---|---|
| `BASE_URL` در `.env` | `https://pay.prostoreshop.site` |
| Callback در پنل ادمین ربات | `https://pay.prostoreshop.site/zarinpal/callback` (یا خالی بگذار تا از BASE_URL ساخته شود) |
| Merchant ID | مرچنت **همان ترمینالی** که دامنه‌اش `pay.prostoreshop.site` است |
| حالت سندباکس | خاموش |

لینک فاکتور حالا این شکلی است: `https://pay.prostoreshop.site/pay/<Authority>` و کاربر از روی دامنه خودت وارد `payment.zarinpal.com/pg/StartPay/...` می‌شود (Referer معتبر).

## ۲) Nginx + SSL برای زیردامنه

رکورد DNS نوع A برای `pay` را به IP سرور بزن (اگر Cloudflare داری، SSL را روی Full (strict) بگذار)، بعد:

```nginx
server {
    listen 80;
    server_name pay.prostoreshop.site;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl http2;
    server_name pay.prostoreshop.site;
    ssl_certificate     /etc/letsencrypt/live/pay.prostoreshop.site/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pay.prostoreshop.site/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d pay.prostoreshop.site
sudo nginx -t && sudo systemctl reload nginx
```

## ۳) تست

```bash
curl -I https://pay.prostoreshop.site/health          # باید 200 بدهد
curl "https://pay.prostoreshop.site/zarinpal/callback?Authority=test&Status=NOK"  # صفحه پرداخت ناموفق
journalctl -u simpars -f
```
