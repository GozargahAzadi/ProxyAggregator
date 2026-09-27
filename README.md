# ProxyAggregator

Public V2Ray/Proxy Config Aggregator that collects, parses, normalizes,
deduplicates, and health-checks public proxy configurations, then publishes
them as subscription files via GitHub.

جمع‌آوری‌کنندهٔ عمومی کانفیگ‌های V2Ray/Proxy: کانفیگ‌های عمومی را جمع‌آوری، تحلیل
(parse)، نرمال‌سازی، حذف تکراری و بررسی سلامت می‌کند و سپس آن‌ها را به‌صورت
فایل‌های اشتراک (Subscription) از طریق GitHub منتشر می‌کند.

## Features

- **Multi-protocol support**: VLESS, VMess, Trojan, Shadowsocks, Hysteria, Hysteria2, SOCKS4, SOCKS5, HTTP, HTTPS
- **Real IP resolution**: Resolves actual endpoint IPs for accurate GeoIP lookup
- **GeoIP enrichment**: MaxMind GeoLite2-based geolocation
- **Health checking**: Latency and connectivity verification
- **Deduplication**: Removes duplicate configurations
- **Subscription output**: Standard proxy subscription formats
- **GitHub Actions native**: Designed to run entirely in CI/CD

## امکانات

- **پشتیبانی از چند پروتکل**: VLESS, VMess, Trojan, Shadowsocks, Hysteria, Hysteria2, SOCKS4, SOCKS5, HTTP, HTTPS
- **تشخیص IP واقعی**: IP واقعی سرورها را برای جست‌وجوی دقیق GeoIP شناسایی می‌کند
- **افزوده‌شدن اطلاعات جغرافیایی (GeoIP)**: مکانیابی بر پایهٔ MaxMind GeoLite2
- **بررسی سلامت**: بررسی تاخیر (Latency) و اتصال‌پذیری
- **حذف تکراری‌ها**: حذف کانفیگ‌های تکراری (Deduplication)
- **خروجی اشتراک**: خروجی در قالب استاندارد فایل‌های Subscription
- **ساخته‌شده برای GitHub Actions**: طراحیشده تا کاملاً در CI/CD اجرا شود

## Subscriptions

Generated subscription feeds are published to the `output/` directory as plain
(newline-delimited URIs), base64 (standard Base64 of the plain feed), and
per-protocol feeds. All files are deterministic and re-generated on every
pipeline run. Every usable URL below sits in its own fenced code block, so
GitHub shows a native Copy button next to it.

فیدهای اشتراک تولیدشده در پوشهٔ `output/` منتشر می‌شوند؛ هم به‌صورت ساده
(URIهای جدا شده با خط جدید)، هم به‌صورت base64 (نسخهٔ استاندارد Base64 فید ساده)
و هم فیدهای مستقل برای هر پروتکل. همهٔ فایل‌ها قطعی (deterministic) هستند و در
هر اجرای pipeline از نو تولید می‌شوند. هر URL قابل استفاده در زیر داخل یک
code block جدا قرار دارد تا GitHub دکمهٔ Copy کنار آن نمایش دهد.

### Combined feeds — فیدهای ترکیبی

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

### Protocol feeds — فیدهای پروتکل

Each protocol below ships a plain feed and its base64 variant. / هر پروتکل در
زیر، هم فید ساده دارد و هم نسخهٔ base64 آن.

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

<!-- PROXYAGGREGATOR: country index start -->
## 🌍 Proxies by Country — کشورها

<br/>

🦋 **Click here to get proxies from a specific country — برای دریافت پروکسی از کشور موردنظر کلیک کنید**

👉 [🌍 Available Countries — کشورهای موجود](./output/countries/README.md)
<!-- PROXYAGGREGATOR: country index end -->

The generated **Available Countries** index above is the single reference for
country subscriptions — it is rebuilt automatically by every Publish run from
the same deduplicated and health-checked proxy set used for the feeds above,
and is never edited by hand. Expand a country to reveal its subscription URLs;
each one sits in its own fenced code block so the country page shows a native
Copy button per URL.

ایندکس **کشورهای موجود (Available Countries)** در بالا مرجع اصلی اشتراک‌های
کشوری است؛ در هر اجرای Publish به‌صورت خودکار از همان مجموعهٔ پروکسی‌های
بدون‌تکراری و بررسی‌سلامت‌شدهٔ فیدهای بالا بازتولید می‌شود و هرگز دستی ویرایش
نمی‌شود. با باز کردن هر کشور، لینک‌های اشتراکش نمایش داده می‌شود؛ هر لینک داخل
یک code block جدا قرار دارد تا GitHub دکمهٔ Copy نشان دهد.

Each non-empty country has its own generated directory under
`output/countries/{CC}/` (uppercase ISO 3166-1 alpha-2), containing:

- `README.md` — a human-readable country page with copyable raw subscription
  URLs for the `all` feed and every available protocol feed
- `all.txt` / `all-base64.txt` — every protocol of that country, plain and base64
- `{protocol}.txt` / `{protocol}-base64.txt` — per-protocol feeds, only when
  that protocol has healthy proxies from that country

Unknown or unrecognized countries are grouped under `XX` (`🌐`) when non-empty;
otherwise that group is omitted.

برای هر کشور دارای پروکسی، پوشهٔ مستقلی در `output/countries/{CC}/` تولید
می‌شود (کد ISO 3166-1 alpha-2 بزرگ)، شامل:

- `README.md` — صفحهٔ کشور به زبان ساده با لینک‌های قابل کپی برای فید `all` و هر فید پروتکل
- `all.txt` / `all-base64.txt` — همهٔ پروتکل‌های آن کشور، ساده و base64
- `{protocol}.txt` / `{protocol}-base64.txt` — فیدهای جداگانهٔ هر پروتکل، فقط وقتی آن پروتکل پروکسی سالم از آن کشور دارد

کشورهای ناشناخته یا غیرقابل‌تشخیص در گروه `XX` (`🌐`) جمع می‌شوند (فقط زمانی که
غیرخالی باشد)؛ وگرنه این گروه حذف می‌شود.

Stable examples — نمونه‌های ثابت (plain and base64 variants exist for each):

DE — README:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/README.md
```

DE — all:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/all.txt
```

DE — all Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/all-base64.txt
```

DE — VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/vless.txt
```

DE — VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/vless-base64.txt
```

US — all:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/all.txt
```

US — VMess:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/vmess.txt
```

## Quick Start — شروع سریع

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/ProxyAggregator.git
cd ProxyAggregator

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check src/ tests/
```

## Configuration

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for all available settings.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architectural overview.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the development plan.

## License

MIT