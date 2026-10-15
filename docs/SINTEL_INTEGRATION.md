# یکپارچه‌سازی API سینتل برای SimPars

## 📋 خلاصه

این مستندات شامل پیاده‌سازی کامل یکپارچه‌سازی API سینتل برای ربات SimPars است که سرویس‌های **تلگرام** و **اینستاگرام** را ارائه می‌دهد.

---

## 🏗️ معماری

### فایل‌های جدید

| فایل | توضیح |
|-------|--------|
| `services/sintel.py` | کلاینت API سینتل با احراز هویت |
| `services/sintel_catalog.py` | مدیریت کاتالوگ و دسته‌بندی سرویس‌ها |
| `services/sintel_orders.py` | مدیریت سفارشات سینتل |
| `handlers/sintel.py` | هندلرهای خرید برای کاربران |
| `handlers/sintel_admin.py` | پنل مدیریت سینتل |
| `tests/test_sintel.py` | تست‌های واحد |

### تغییرات فایل‌های موجود

| فایل | تغییر |
|-------|--------|
| `keyboards.py` | افزودن کیبوردهای سینتل |
| `database.py` | افزودن جداول `sintel_services` و `sintel_orders` |
| `bot.py` | ثبت روترهای جدید سینتل |
| `handlers/__init__.py` | صادرات هندلرهای جدید |
| `services/__init__.py` | صادرات سرویس‌های جدید |

---

## 🔌 API سینتل

### اطلاعات تأیید شده

```
آدرس API: https://sintell.ir/panel/api.php
احراز هویت: کلید API در POST body
متد: HTTP POST
فرمت پاسخ: JSON
```

### اکشن‌های پشتیبانی شده

| اکشن | پارامترها | توضیح |
|------|----------|--------|
| `balance` | - | موجودی کیف پول |
| `services` | `lang` (اختیاری) | لیست سرویس‌ها |
| `add` | `service`, `link`, `quantity` | ثبت سفارش |
| `status` | `order` یا `orders=1,2,3` | وضعیت سفارش |
| `refill` | `order` | درخواست ریفیل |
| `cancel` | `orders=1,2` | لغو سفارش |

### قیمت‌گذاری

```
فرمول: rate × quantity ÷ 1000
واحد: تومان (IRT)
```

---

## 📊 جداول دیتابیس

### sintel_services

```sql
CREATE TABLE sintel_services(
    service_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    rate TEXT NOT NULL,
    min_quantity INTEGER NOT NULL,
    max_quantity INTEGER NOT NULL,
    platform TEXT NOT NULL DEFAULT 'telegram',
    subcategory TEXT NOT NULL DEFAULT 'other',
    extra_data TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
```

### sintel_orders

```sql
CREATE TABLE sintel_orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider_order_id TEXT NOT NULL,
    service_id INTEGER NOT NULL,
    link TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    provider_cost INTEGER NOT NULL,
    selling_price INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    remains INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    completed_at INTEGER
);
```

---

## 🎯 دسته‌بندی سرویس‌ها

### تلگرام
- 👥 اعضای کانال و گروه
- 👁️ بازدید پست
- ❤️ ریاکشن و احساس
- 💬 کامنت و نظر
- 📤 اشتراک‌گذاری
- 📊 سایر خدمات

### اینستاگرام
- 👥 فالوور
- ❤️ لایک
- 👁️ بازدید
- 💬 کامنت
- 📱 استوری
- 📊 سایر خدمات

---

## 🔒 امنیت

### نکات مهم

1. **کلید API**: هرگز در لاگ‌ها نمایش داده نمی‌شود
2. **ماسک کردن**: کلید در رابط کاربری ماسک می‌شود (`AP••••••••12`)
3. **حذف پیام**: پیام‌های حاوی کلید API پس از ذخیره حذف می‌شوند
4. **دسترسی ادمین**: تمام عملیات مدیریتی نیاز به احراز هویت ادمین دارند
5. **Transaction**: کسر موجودی و ثبت سفارش به صورت اتمیک انجام می‌شود

---

## 📝 دستورات مستندات سینتل

### تست API

```python
from services.sintel import SintelClient

async def test():
    client = SintelClient("YOUR_API_KEY")
    balance = await client.get_balance()
    print(f"موجودی: {balance}")
```

### همگام‌سازی کاتالوگ

```python
from services.sintel_catalog import sync_catalog_from_provider

result = await sync_catalog_from_provider("YOUR_API_KEY")
print(f"موفقیت: {result['success']}")
print(f"تلگرام: {result['telegram']}")
print(f"اینستاگرام: {result['instagram']}")
```

---

## ⚠️ نکات مهم پیاده‌سازی

### Rate Limiting
- حداکثر ۱۲۰ درخواست در دقیقه
- از کش استفاده کنید (TTL پیشنهادی: ۵ دقیقه)

### Idempotency
- قبل از retry، وضعیت سفارش را بررسی کنید
- از شناسه یکتا برای جلوگیری از سفارش تکراری استفاده کنید

### Error Handling
- تمام خطاها را به پیام‌های فارسی تبدیل کنید
- در صورت خطای شبکه، موجودی را برگردانید

---

## 🧪 تست

```bash
# اجرای تست‌ها
pytest tests/test_sintel.py -v

# اجرا با کاوریج
pytest tests/test_sintel.py --cov=services --cov=handlers
```

---

## 📞 پشتیبانی

برای مشکلات یا سؤالات:
- مستندات API: https://sintell.ir/blog/smm-api
- پنل کاربری: https://sintell.ir/panel
