# پروکسی‌اگریگیتور (ProxyAggregator)

[English](./README.md) | **فارسی**

جمع‌آوری‌کنندهٔ عمومی کانفیگ‌های V2Ray/Proxy: کانفیگ‌های عمومی را جمع‌آوری،
تحلیل (parse)، نرمال‌سازی، حذف تکراری و بررسی سلامت می‌کند و سپس آن‌ها را
به‌صورت فایل‌های اشتراک (Subscription) از طریق GitHub منتشر می‌کند.

## امکانات

- **پشتیبانی از چند پروتکل**: VLESS، VMess، Trojan، Shadowsocks، Hysteria، Hysteria2، SOCKS4، SOCKS5، HTTP، HTTPS
- **تشخیص IP واقعی**: IP واقعی سرورها را برای جست‌وجوی دقیق GeoIP شناسایی می‌کند
- **افزوده‌شدن اطلاعات جغرافیایی (GeoIP)**: مکان‌یابی بر پایهٔ MaxMind GeoLite2
- **بررسی سلامت**: بررسی تاخیر (Latency) و اتصال‌پذیری
- **حذف تکراری‌ها**: حذف کانفیگ‌های تکراری (Deduplication)
- **خروجی اشتراک**: خروجی در قالب استاندارد فایل‌های Subscription
- **ساخته‌شده برای GitHub Actions**: طراحی‌شده تا کاملاً در CI/CD اجرا شود

## اشتراک‌ها

فیدهای اشتراک تولیدشده در پوشهٔ `output/` منتشر می‌شوند؛ هم به‌صورت ساده
(URIهای جدا شده با خط جدید)، هم به‌صورت base64 (نسخهٔ استاندارد Base64 فید
ساده) و هم فیدهای مستقل برای هر پروتکل. همهٔ فایل‌ها قطعی (deterministic)
هستند و در هر اجرای pipeline از نو تولید می‌شوند. هر URL قابل استفاده در زیر
داخل یک code block جدا قرار دارد تا GitHub دکمهٔ Copy کنار آن نمایش دهد.

### فیدهای ترکیبی

ProxyAggregator:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.txt
```

ProxyAggregator Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator-base64.txt
```

ProxyAggregator JSON:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.json
```

Manifest (JSON):

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/manifest.json
```

### فیدهای پروتکل

هر پروتکل در زیر، هم فید ساده دارد و هم نسخهٔ base64 آن.

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vless-base64.txt
```

VMess:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vmess.txt
```

VMess Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vmess-base64.txt
```

Trojan:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/trojan.txt
```

Trojan Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/trojan-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/shadowsocks-base64.txt
```

Hysteria:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria.txt
```

Hysteria Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria-base64.txt
```

Hysteria2:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria2.txt
```

Hysteria2 Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria2-base64.txt
```

SOCKS4:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks4.txt
```

SOCKS4 Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks4-base64.txt
```

SOCKS5:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks5.txt
```

SOCKS5 Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks5-base64.txt
```

HTTP:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/http.txt
```

HTTP Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/http-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/https-base64.txt
```

## شروع سریع

```bash
# کلون کردن مخزن
git clone https://github.com/YOUR_USERNAME/ProxyAggregator.git
cd ProxyAggregator

# نصب وابستگی‌ها
uv sync

# اجرای تست‌ها
uv run pytest

# اجرای لینتر
uv run ruff check src/ tests/
```

## پیکربندی

همهٔ تنظیمات موجود در [docs/CONFIGURATION.md](docs/CONFIGURATION.md) (به انگلیسی).

## معماری

نمای کلی معماری در [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (به انگلیسی).

## نقشه راه

برنامهٔ توسعه در [ROADMAP.md](ROADMAP.md) (به انگلیسی).

## مجوز

MIT