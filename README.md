# 🚀 ProxyAggregator

**English** | [فارسی](./README.fa.md)

> Free, automatic aggregator of public V2Ray & proxy configurations  
> Collects → Parses → Deduplicates → Health-checks → Publishes subscription feeds every ~15 minutes

[![GitHub stars](https://img.shields.io/github/stars/GozargahAzadi/ProxyAggregator?style=flat-square&logo=github)](https://github.com/GozargahAzadi/ProxyAggregator)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Last Publish](https://img.shields.io/badge/Last%20Publish-2026--09--28-brightgreen)](https://github.com/GozargahAzadi/ProxyAggregator/commits/main)
[![Python](https://img.shields.io/badge/Python-3.12+-blue)](https://www.python.org/)

---

## 🔥 Ready-to-use Subscription Links

### Recommended (All Protocols)

| Format | Link |
|--------|------|
| **Plain** | ```https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.txt``` |
| **Base64** | ```https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator-base64.txt``` |
| **JSON** | ```https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.json``` |
| **Manifest** | ```https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/manifest.json``` |

### By Protocol

<details>
<summary>Click to expand protocol-specific feeds</summary>

| Protocol | Plain | Base64 |
|----------|-------|--------|
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

### By Country

🦋 **[View all countries with healthy proxies →](./output/countries/README.md)**

> Country feeds are rebuilt on every successful publish, so this page is the
> live, always-current index of which countries currently have healthy proxies.
> Countries and protocols without eligible proxies are removed automatically.
> This README is hand-maintained and only changes when the project docs do.

---

## 📱 How to Use

1. Copy one of the links above.
2. Open your client (v2rayNG, Nekobox, Hiddify, Streisand, Clash Meta, Sing-box, ...).
3. Go to **Subscription** / **Profiles** → Add new subscription.
4. Paste the link and update.
5. Connect and enjoy.

> Only proxies that successfully passed real health checks are published.

---

## ✨ Features

- **Multi-protocol support**: VLESS, VMess, Trojan, Shadowsocks, Hysteria, Hysteria2, SOCKS4/5, HTTP/HTTPS
- **Real IP resolution** for accurate GeoIP
- **MaxMind GeoLite2** geolocation enrichment
- **Real health checking** (TCP + TLS + protocol-level checks + latency)
- **Smart deduplication**
- **Clean subscription outputs** (Plain, Base64, JSON)
- **Country-based feeds**
- **Fully automated** via GitHub Actions (no personal server needed)
- **Deterministic & reproducible** builds

---

## 🛠️ For Developers

```bash
# Clone
git clone https://github.com/GozargahAzadi/ProxyAggregator.git
cd ProxyAggregator

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run full pipeline locally
uv run python -m proxyaggregator pipeline
```

### Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | High-level design |
| [Configuration](docs/CONFIGURATION.md) | Settings & environment |
| [Sources](docs/SOURCES.md) | How sources are managed |
| [Publisher](docs/PUBLISHER.md) | Publishing & release process |
| [Scoring](docs/SCORING.md) | Ranking algorithm |
| [Subscription](docs/SUBSCRIPTION.md) | Output formats |
| [Database](docs/DATABASE.md) | Schema & migrations |

---

## 📄 License

MIT License — free for personal and commercial use.
