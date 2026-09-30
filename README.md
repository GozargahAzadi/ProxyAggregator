# 🚀 ProxyAggregator

**English** | [فارسی](./README.fa.md)

> Free, automatic aggregator of public V2Ray & proxy configurations  
> Collects → Parses → Deduplicates → Health-checks → Publishes subscription feeds every ~15 minutes

[![GitHub stars](https://img.shields.io/github/stars/GozargahAzadi/ProxyAggregator?style=social)](https://github.com/GozargahAzadi/ProxyAggregator)
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

<!-- PROXYAGGREGATOR: country index start -->
## 🌍 Proxies by Country

Full flag map of every ISO-3166-1 country — a country links to its page only when it has healthy proxies in the current publish run:

<details>
<summary>🌐 All countries — full ISO flag map</summary>

- 🇦🇩 Andorra
- 🇦🇪 [United Arab Emirates](./output/countries/AE/)
- 🇦🇫 Afghanistan
- 🇦🇬 Antigua and Barbuda
- 🇦🇮 Anguilla
- 🇦🇱 Albania
- 🇦🇲 Armenia
- 🇦🇴 Angola
- 🇦🇶 Antarctica
- 🇦🇷 Argentina
- 🇦🇸 American Samoa
- 🇦🇹 [Austria](./output/countries/AT/)
- 🇦🇺 Australia
- 🇦🇼 Aruba
- 🇦🇽 Aland Islands
- 🇦🇿 Azerbaijan
- 🇧🇦 Bosnia and Herzegovina
- 🇧🇧 Barbados
- 🇧🇩 Bangladesh
- 🇧🇪 [Belgium](./output/countries/BE/)
- 🇧🇫 Burkina Faso
- 🇧🇬 [Bulgaria](./output/countries/BG/)
- 🇧🇭 Bahrain
- 🇧🇮 Burundi
- 🇧🇯 Benin
- 🇧🇱 Saint Barthelemy
- 🇧🇲 Bermuda
- 🇧🇳 Brunei Darussalam
- 🇧🇴 Bolivia
- 🇧🇶 Bonaire, Sint Eustatius and Saba
- 🇧🇷 Brazil
- 🇧🇸 Bahamas
- 🇧🇹 Bhutan
- 🇧🇻 Bouvet Island
- 🇧🇼 Botswana
- 🇧🇾 Belarus
- 🇧🇿 Belize
- 🇨🇦 [Canada](./output/countries/CA/)
- 🇨🇨 Cocos (Keeling) Islands
- 🇨🇩 Congo, Democratic Republic of the
- 🇨🇫 Central African Republic
- 🇨🇬 Congo
- 🇨🇭 [Switzerland](./output/countries/CH/)
- 🇨🇮 Cote d'Ivoire
- 🇨🇰 Cook Islands
- 🇨🇱 Chile
- 🇨🇲 Cameroon
- 🇨🇳 China
- 🇨🇴 Colombia
- 🇨🇷 Costa Rica
- 🇨🇺 Cuba
- 🇨🇻 Cabo Verde
- 🇨🇼 Curacao
- 🇨🇽 Christmas Island
- 🇨🇾 Cyprus
- 🇨🇿 Czechia
- 🇩🇪 [Germany](./output/countries/DE/)
- 🇩🇯 Djibouti
- 🇩🇰 Denmark
- 🇩🇲 Dominica
- 🇩🇴 Dominican Republic
- 🇩🇿 Algeria
- 🇪🇨 Ecuador
- 🇪🇪 [Estonia](./output/countries/EE/)
- 🇪🇬 Egypt
- 🇪🇭 Western Sahara
- 🇪🇷 Eritrea
- 🇪🇸 [Spain](./output/countries/ES/)
- 🇪🇹 Ethiopia
- 🇫🇮 Finland
- 🇫🇯 Fiji
- 🇫🇰 Falkland Islands (Malvinas)
- 🇫🇲 Micronesia
- 🇫🇴 Faroe Islands
- 🇫🇷 [France](./output/countries/FR/)
- 🇬🇦 Gabon
- 🇬🇧 [United Kingdom](./output/countries/GB/)
- 🇬🇩 Grenada
- 🇬🇪 Georgia
- 🇬🇫 French Guiana
- 🇬🇬 Guernsey
- 🇬🇭 Ghana
- 🇬🇮 Gibraltar
- 🇬🇱 Greenland
- 🇬🇲 Gambia
- 🇬🇳 Guinea
- 🇬🇵 Guadeloupe
- 🇬🇶 Equatorial Guinea
- 🇬🇷 Greece
- 🇬🇸 South Georgia and the South Sandwich Islands
- 🇬🇹 Guatemala
- 🇬🇺 Guam
- 🇬🇼 Guinea-Bissau
- 🇬🇾 Guyana
- 🇭🇰 Hong Kong
- 🇭🇲 Heard Island and McDonald Islands
- 🇭🇳 Honduras
- 🇭🇷 [Croatia](./output/countries/HR/)
- 🇭🇹 Haiti
- 🇭🇺 Hungary
- 🇮🇩 Indonesia
- 🇮🇪 [Ireland](./output/countries/IE/)
- 🇮🇱 Israel
- 🇮🇲 Isle of Man
- 🇮🇳 India
- 🇮🇴 British Indian Ocean Territory
- 🇮🇶 Iraq
- 🇮🇷 [Iran](./output/countries/IR/)
- 🇮🇸 Iceland
- 🇮🇹 Italy
- 🇯🇪 Jersey
- 🇯🇲 Jamaica
- 🇯🇴 Jordan
- 🇯🇵 [Japan](./output/countries/JP/)
- 🇰🇪 Kenya
- 🇰🇬 Kyrgyzstan
- 🇰🇭 Cambodia
- 🇰🇮 Kiribati
- 🇰🇲 Comoros
- 🇰🇳 Saint Kitts and Nevis
- 🇰🇵 Korea, Democratic People's Republic of
- 🇰🇷 [Korea, Republic of](./output/countries/KR/)
- 🇰🇼 Kuwait
- 🇰🇾 Cayman Islands
- 🇰🇿 Kazakhstan
- 🇱🇦 Lao People's Democratic Republic
- 🇱🇧 Lebanon
- 🇱🇨 Saint Lucia
- 🇱🇮 Liechtenstein
- 🇱🇰 Sri Lanka
- 🇱🇷 Liberia
- 🇱🇸 Lesotho
- 🇱🇹 [Lithuania](./output/countries/LT/)
- 🇱🇺 Luxembourg
- 🇱🇻 Latvia
- 🇱🇾 Libya
- 🇲🇦 Morocco
- 🇲🇨 Monaco
- 🇲🇩 Moldova
- 🇲🇪 Montenegro
- 🇲🇫 Saint Martin (French part)
- 🇲🇬 Madagascar
- 🇲🇭 Marshall Islands
- 🇲🇰 North Macedonia
- 🇲🇱 Mali
- 🇲🇲 Myanmar
- 🇲🇳 Mongolia
- 🇲🇴 Macao
- 🇲🇵 Northern Mariana Islands
- 🇲🇶 Martinique
- 🇲🇷 Mauritania
- 🇲🇸 Montserrat
- 🇲🇹 Malta
- 🇲🇺 Mauritius
- 🇲🇻 Maldives
- 🇲🇼 Malawi
- 🇲🇽 Mexico
- 🇲🇾 Malaysia
- 🇲🇿 Mozambique
- 🇳🇦 Namibia
- 🇳🇨 New Caledonia
- 🇳🇪 Niger
- 🇳🇫 Norfolk Island
- 🇳🇬 Nigeria
- 🇳🇮 Nicaragua
- 🇳🇱 [Netherlands](./output/countries/NL/)
- 🇳🇴 Norway
- 🇳🇵 Nepal
- 🇳🇷 Nauru
- 🇳🇺 Niue
- 🇳🇿 New Zealand
- 🇴🇲 Oman
- 🇵🇦 [Panama](./output/countries/PA/)
- 🇵🇪 Peru
- 🇵🇫 French Polynesia
- 🇵🇬 Papua New Guinea
- 🇵🇭 Philippines
- 🇵🇰 Pakistan
- 🇵🇱 Poland
- 🇵🇲 Saint Pierre and Miquelon
- 🇵🇳 Pitcairn
- 🇵🇷 Puerto Rico
- 🇵🇸 Palestine
- 🇵🇹 [Portugal](./output/countries/PT/)
- 🇵🇼 Palau
- 🇵🇾 Paraguay
- 🇶🇦 Qatar
- 🇷🇪 Reunion
- 🇷🇴 [Romania](./output/countries/RO/)
- 🇷🇸 Serbia
- 🇷🇺 [Russia](./output/countries/RU/)
- 🇷🇼 Rwanda
- 🇸🇦 Saudi Arabia
- 🇸🇧 Solomon Islands
- 🇸🇨 [Seychelles](./output/countries/SC/)
- 🇸🇩 Sudan
- 🇸🇪 [Sweden](./output/countries/SE/)
- 🇸🇬 [Singapore](./output/countries/SG/)
- 🇸🇭 Saint Helena, Ascension and Tristan da Cunha
- 🇸🇮 Slovenia
- 🇸🇯 Svalbard and Jan Mayen
- 🇸🇰 Slovakia
- 🇸🇱 Sierra Leone
- 🇸🇲 San Marino
- 🇸🇳 Senegal
- 🇸🇴 Somalia
- 🇸🇷 Suriname
- 🇸🇸 South Sudan
- 🇸🇹 Sao Tome and Principe
- 🇸🇻 El Salvador
- 🇸🇽 Sint Maarten (Dutch part)
- 🇸🇾 Syrian Arab Republic
- 🇸🇿 Eswatini
- 🇹🇨 Turks and Caicos Islands
- 🇹🇩 Chad
- 🇹🇫 French Southern Territories
- 🇹🇬 Togo
- 🇹🇭 Thailand
- 🇹🇯 Tajikistan
- 🇹🇰 Tokelau
- 🇹🇱 Timor-Leste
- 🇹🇲 Turkmenistan
- 🇹🇳 Tunisia
- 🇹🇴 Tonga
- 🇹🇷 [Turkey](./output/countries/TR/)
- 🇹🇹 Trinidad and Tobago
- 🇹🇻 Tuvalu
- 🇹🇼 Taiwan
- 🇹🇿 Tanzania
- 🇺🇦 Ukraine
- 🇺🇬 Uganda
- 🇺🇲 United States Minor Outlying Islands
- 🇺🇸 [United States](./output/countries/US/)
- 🇺🇾 Uruguay
- 🇺🇿 Uzbekistan
- 🇻🇦 Holy See
- 🇻🇨 Saint Vincent and the Grenadines
- 🇻🇪 Venezuela
- 🇻🇬 Virgin Islands, British
- 🇻🇮 Virgin Islands, U.S.
- 🇻🇳 Vietnam
- 🇻🇺 Vanuatu
- 🇼🇫 Wallis and Futuna
- 🇼🇸 Samoa
- 🇽🇰 Kosovo
- 🇾🇪 Yemen
- 🇾🇹 Mayotte
- 🇿🇦 [South Africa](./output/countries/ZA/)
- 🇿🇲 Zambia
- 🇿🇼 Zimbabwe

</details>

🦋 Click here to get proxies from a specific country

<details>
<summary>🇦🇪 United Arab Emirates — 2 proxies</summary>

### 🇦🇪 United Arab Emirates

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AE/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AE/all-base64.txt
```

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AE/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AE/vless-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AE/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AE/https-base64.txt
```

</details>

<details>
<summary>🇦🇹 Austria — 1 proxy</summary>

### 🇦🇹 Austria

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AT/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AT/all-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AT/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AT/https-base64.txt
```

</details>

<details>
<summary>🇧🇪 Belgium — 1 proxy</summary>

### 🇧🇪 Belgium

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/BE/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/BE/all-base64.txt
```

HTTP:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/BE/http.txt
```

HTTP Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/BE/http-base64.txt
```

</details>

<details>
<summary>🇧🇬 Bulgaria — 2 proxies</summary>

### 🇧🇬 Bulgaria

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/BG/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/BG/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/BG/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/BG/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇨🇦 Canada — 18 proxies</summary>

### 🇨🇦 Canada

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CA/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CA/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CA/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CA/shadowsocks-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CA/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CA/https-base64.txt
```

</details>

<details>
<summary>🇨🇭 Switzerland — 2 proxies</summary>

### 🇨🇭 Switzerland

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CH/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CH/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CH/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CH/shadowsocks-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CH/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CH/https-base64.txt
```

</details>

<details>
<summary>🇩🇪 Germany — 8 proxies</summary>

### 🇩🇪 Germany

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/all-base64.txt
```

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/vless-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇪🇪 Estonia — 1 proxy</summary>

### 🇪🇪 Estonia

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/EE/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/EE/all-base64.txt
```

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/EE/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/EE/vless-base64.txt
```

</details>

<details>
<summary>🇪🇸 Spain — 2 proxies</summary>

### 🇪🇸 Spain

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/ES/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/ES/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/ES/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/ES/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇫🇷 France — 15 proxies</summary>

### 🇫🇷 France

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/FR/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/FR/all-base64.txt
```

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/FR/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/FR/vless-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/FR/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/FR/shadowsocks-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/FR/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/FR/https-base64.txt
```

</details>

<details>
<summary>🇬🇧 United Kingdom — 75 proxies</summary>

### 🇬🇧 United Kingdom

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/GB/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/GB/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/GB/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/GB/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇭🇷 Croatia — 1 proxy</summary>

### 🇭🇷 Croatia

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/HR/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/HR/all-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/HR/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/HR/https-base64.txt
```

</details>

<details>
<summary>🇮🇪 Ireland — 1 proxy</summary>

### 🇮🇪 Ireland

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IE/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IE/all-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IE/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IE/https-base64.txt
```

</details>

<details>
<summary>🇮🇷 Iran — 10 proxies</summary>

### 🇮🇷 Iran

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IR/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IR/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IR/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IR/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇯🇵 Japan — 3 proxies</summary>

### 🇯🇵 Japan

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/JP/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/JP/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/JP/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/JP/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇰🇷 Korea, Republic of — 4 proxies</summary>

### 🇰🇷 Korea, Republic of

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/KR/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/KR/all-base64.txt
```

VMess:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/KR/vmess.txt
```

VMess Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/KR/vmess-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/KR/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/KR/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇱🇹 Lithuania — 1 proxy</summary>

### 🇱🇹 Lithuania

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/LT/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/LT/all-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/LT/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/LT/https-base64.txt
```

</details>

<details>
<summary>🇳🇱 Netherlands — 22 proxies</summary>

### 🇳🇱 Netherlands

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/NL/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/NL/all-base64.txt
```

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/NL/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/NL/vless-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/NL/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/NL/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇵🇦 Panama — 1 proxy</summary>

### 🇵🇦 Panama

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PA/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PA/all-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PA/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PA/https-base64.txt
```

</details>

<details>
<summary>🇵🇹 Portugal — 1 proxy</summary>

### 🇵🇹 Portugal

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PT/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PT/all-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PT/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PT/https-base64.txt
```

</details>

<details>
<summary>🇷🇴 Romania — 2 proxies</summary>

### 🇷🇴 Romania

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/RO/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/RO/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/RO/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/RO/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇷🇺 Russia — 4 proxies</summary>

### 🇷🇺 Russia

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/RU/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/RU/all-base64.txt
```

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/RU/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/RU/vless-base64.txt
```

</details>

<details>
<summary>🇸🇨 Seychelles — 2 proxies</summary>

### 🇸🇨 Seychelles

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SC/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SC/all-base64.txt
```

VMess:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SC/vmess.txt
```

VMess Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SC/vmess-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SC/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SC/https-base64.txt
```

</details>

<details>
<summary>🇸🇪 Sweden — 1 proxy</summary>

### 🇸🇪 Sweden

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SE/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SE/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SE/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SE/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇸🇬 Singapore — 12 proxies</summary>

### 🇸🇬 Singapore

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SG/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SG/all-base64.txt
```

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SG/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SG/vless-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SG/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SG/shadowsocks-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SG/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SG/https-base64.txt
```

</details>

<details>
<summary>🇹🇷 Turkey — 2 proxies</summary>

### 🇹🇷 Turkey

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/TR/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/TR/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/TR/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/TR/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇺🇸 United States — 191 proxies</summary>

### 🇺🇸 United States

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/all-base64.txt
```

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/vless-base64.txt
```

VMess:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/vmess.txt
```

VMess Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/vmess-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/shadowsocks-base64.txt
```

HTTP:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/http.txt
```

HTTP Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/http-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/https-base64.txt
```

</details>

<details>
<summary>🇿🇦 South Africa — 3 proxies</summary>

### 🇿🇦 South Africa

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/ZA/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/ZA/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/ZA/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/ZA/shadowsocks-base64.txt
```

</details>

<!-- PROXYAGGREGATOR: country index end -->
