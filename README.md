# 📱 SimPars Bot | ربات فروش شماره مجازی

🤖 [@SimParsBot](https://t.me/SimParsBot) • 📢 [@SimPars](https://t.me/SimPars) • 📸 [@SimPars.ir](https://instagram.com/SimPars.ir)

ربات تلگرامی فروش خودکار شماره مجازی با اتصال به **API سایت 5Sim** و درگاه پرداخت **زیبال**.

## ✨ امکانات کاربران
- 🛒 خرید شماره مجازی برای سرویس‌های پرطرفدار از کشورهای مختلف
- 💹 قیمت لحظه‌ای، مرتب‌شده از ارزان‌ترین، با صفحه‌بندی
- 📩 دریافت **خودکار** کد تایید
- 🛡 **بازگشت خودکار وجه** در صورت عدم دریافت کد + امکان لغو دستی
- 💰 کیف پول و شارژ آنلاین با زیبال
- 🎁 دعوت دوستان با پاداش درصدی از شارژ
- 📦 تاریخچه سفارش، 👤 حساب کاربری، 💬 پشتیبانی، 📚 راهنما
- 🔒 جوین اجباری کانال

## ⚙️ پنل مدیریت (`/admin`)
- 🔑 ثبت/حذف API 5Sim + نمایش وضعیت و موجودی پنل
- 💳 ثبت مرچنت زیبال، حالت تست، آدرس بازگشت
- 💹 نرخ تبدیل، درصد سود، حداقل/حداکثر شارژ، درصد دعوت
- 📊 آمار کامل
- 👥 مدیریت کاربران: جستجو، افزایش/کسر موجودی، مسدودسازی
- 📢 پیام همگانی (متن، عکس، ویدیو، فایل)
- 🔒 جوین اجباری و 🛠 حالت تعمیرات

## 🧱 تکنولوژی
Python 3.10+ • aiogram 3 • SQLite • aiohttp

## 🚀 نصب سریع
```bash
git clone https://github.com/arjeyproject/SimPars.git
cd SimPars
sudo bash install.sh
```
📘 آموزش کامل قدم‌به‌قدم: [INSTALL.md](INSTALL.md)

## 📂 ساختار
```
SimPars/
├── bot.py          # فایل اصلی
├── config.py       # تنظیمات (.env)
├── database.py     # دیتابیس SQLite
├── keyboards.py    # دکمه‌های شیشه‌ای
├── texts.py        # متن‌ها، سرویس‌ها، کشورها
├── middlewares.py  # جوین اجباری، مسدودی، تعمیرات، رفرال
├── workers.py      # بررسی خودکار سفارش‌ها
├── webserver.py    # Callback درگاه زیبال
├── handlers/       # user • buy • wallet • admin • fallback
└── services/       # fivesim • zibal • orders • payments
```

---
👨‍💻 مالک: [@iRezaFattahi](https://t.me/iRezaFattahi)
