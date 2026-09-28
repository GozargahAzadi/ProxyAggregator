# 🚀 پروکسی‌اگریگیتور (ProxyAggregator)

[English](./README.md) | **فارسی**

> جمع‌آوری‌کننده رایگان و خودکار کانفیگ‌های عمومی V2Ray و پروکسی  
> جمع‌آوری → پارس → حذف تکراری → بررسی سلامت واقعی → انتشار اشتراک‌ها هر حدود ۱۵ دقیقه

[![GitHub stars](https://img.shields.io/github/stars/GozargahAzadi/ProxyAggregator?style=social)](https://github.com/GozargahAzadi/ProxyAggregator)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Last Publish](https://img.shields.io/badge/Last%20Publish-2026--09--28-brightgreen)](https://github.com/GozargahAzadi/ProxyAggregator/commits/main)
[![Python](https://img.shields.io/badge/Python-3.12+-blue)](https://www.python.org/)

---

## 🔥 لینک‌های آماده اشتراک (کپی و استفاده)

### پیشنهادی (همه پروتکل‌ها)

| فرمت | لینک |
|------|------|
| **ساده (Plain)** | ```https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.txt``` |
| **Base64** | ```https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator-base64.txt``` |
| **JSON** | ```https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.json``` |
| **Manifest** | ```https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/manifest.json``` |

### بر اساس پروتکل

<details>
<summary>کلیک کنید تا لینک‌های جداگانه هر پروتکل را ببینید</summary>

| پروتکل | ساده (Plain) | Base64 |
|--------|--------------|--------|
| **VLESS** | [vless.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vless.txt) | [vless-base64.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vless-base64.txt) |
| **VMess** | [vmess.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vmess.txt) | [vmess-base64.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vmess-base64.txt) |
| **Trojan** | [trojan.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/trojan.txt) | [trojan-base64.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/trojan-base64.txt) |
| **Shadowsocks** | [shadowsocks.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/shadowsocks.txt) | [shadowsocks-base64.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/shadowsocks-base64.txt) |
| **Hysteria** | [hysteria.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria.txt) | [hysteria-base64.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria-base64.txt) |
| **Hysteria2** | [hysteria2.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria2.txt) | [hysteria2-base64.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria2-base64.txt) |
| **SOCKS4** | [socks4.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks4.txt) | [socks4-base64.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks4-base64.txt) |
| **SOCKS5** | [socks5.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks5.txt) | [socks5-base64.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks5-base64.txt) |
| **HTTP** | [http.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/http.txt) | [http-base64.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/http-base64.txt) |
| **HTTPS** | [https.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/https.txt) | [https-base64.txt](https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/https-base64.txt) |

</details>

### بر اساس کشور

🦋 **[مشاهده همه کشورها و پروکسی‌های سالم →](./output/countries/README.md)**

---

## 📱 چطور استفاده کنم؟

1. یکی از لینک‌های بالا را کپی کنید.
2. اپلیکیشن خود را باز کنید (v2rayNG، Nekobox، Hiddify، Streisand، Clash Meta، Sing-box و ...).
3. به بخش **اشتراک (Subscription)** یا **Profiles** بروید و اشتراک جدید اضافه کنید.
4. لینک را Paste کرده و Update بزنید.
5. وصل شوید و لذت ببرید.

> فقط پروکسی‌هایی که از بررسی سلامت واقعی عبور کرده‌اند در خروجی قرار می‌گیرند.

---

## ✨ امکانات

- پشتیبانی از بیش از ۱۰ پروتکل محبوب
- تشخیص IP واقعی سرور برای GeoIP دقیق
- مکان‌یابی با MaxMind GeoLite2
- بررسی سلامت واقعی (TCP + TLS + سطح پروتکل + اندازه‌گیری latency)
- حذف هوشمند کانفیگ‌های تکراری
- خروجی تمیز و استاندارد (Plain، Base64، JSON)
- فیدهای جداگانه بر اساس کشور
- اجرای کامل و خودکار روی GitHub Actions (بدون نیاز به سرور شخصی)
- ساخت deterministic و قابل بازتولید

---

## 🛠️ برای توسعه‌دهندگان

```bash
# کلون کردن مخزن
git clone https://github.com/GozargahAzadi/ProxyAggregator.git
cd ProxyAggregator

# نصب وابستگی‌ها
uv sync

# اجرای تست‌ها
uv run pytest

# اجرای کامل پایپ‌لاین به صورت محلی
uv run python -m proxyaggregator pipeline
```

### مستندات

| سند | توضیح |
|-----|-------|
| [معماری](docs/ARCHITECTURE.md) | طراحی کلی سیستم |
| [پیکربندی](docs/CONFIGURATION.md) | تنظیمات و متغیرهای محیطی |
| [منابع](docs/SOURCES.md) | مدیریت منابع ورودی |
| [ناشر](docs/PUBLISHER.md) | فرآیند انتشار و ریلیز |
| [امتیازدهی](docs/SCORING.md) | الگوریتم رتبه‌بندی |
| [اشتراک](docs/SUBSCRIPTION.md) | فرمت‌های خروجی |
| [دیتابیس](docs/DATABASE.md) | ساختار و مایگریشن‌ها |

---

## 📄 مجوز

MIT License — رایگان برای استفاده شخصی و تجاری.
