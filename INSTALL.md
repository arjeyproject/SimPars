# نصب SimPars با زرین‌پال

نصب قبلی را انجام بده، اما به‌جای زیبال از زرین‌پال استفاده کن:

```bash
cd /root/SimPars
git pull origin main
sudo systemctl restart simpars
```

در تلگرام `/admin` را بفرست، وارد **تنظیمات درگاه زرین‌پال** شو و Merchant ID را ثبت کن. آدرس callback باید این باشد:

```text
https://prostoreshop.site/zarinpal/callback
```

قبل از تست، DNS دامنه و SSL باید فعال باشد و پورت وب‌سرور ربات (`WEB_PORT`) از اینترنت قابل دسترسی باشد. برای مشاهده خطاها:

```bash
journalctl -u simpars -f
```
