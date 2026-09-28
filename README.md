# ProxyAggregator

**English** | [فارسی](./README.fa.md)

Public V2Ray/Proxy Config Aggregator that collects, parses, normalizes,
deduplicates, and health-checks public proxy configurations, then publishes
them as subscription files via GitHub.

## Features

- **Multi-protocol support**: VLESS, VMess, Trojan, Shadowsocks, Hysteria, Hysteria2, SOCKS4, SOCKS5, HTTP, HTTPS
- **Real IP resolution**: Resolves actual endpoint IPs for accurate GeoIP lookup
- **GeoIP enrichment**: MaxMind GeoLite2-based geolocation
- **Health checking**: Latency and connectivity verification
- **Deduplication**: Removes duplicate configurations
- **Subscription output**: Standard proxy subscription formats
- **GitHub Actions native**: Designed to run entirely in CI/CD

## Subscriptions

Generated subscription feeds are published to the `output/` directory as plain
(newline-delimited URIs), base64 (standard Base64 of the plain feed), and
per-protocol feeds. All files are deterministic and re-generated on every
pipeline run. Every usable URL below sits in its own fenced code block, so
GitHub shows a native Copy button next to it.

### Combined feeds

ProxyAggregator — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.txt
```

ProxyAggregator — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator-base64.txt
```

ProxyAggregator — JSON

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.json
```

Manifest — JSON

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/manifest.json
```

### Protocol feeds

Each protocol below ships a plain feed and its base64 variant.

VLESS — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vless.txt
```

VLESS — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vless-base64.txt
```

VMess — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vmess.txt
```

VMess — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vmess-base64.txt
```

Trojan — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/trojan.txt
```

Trojan — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/trojan-base64.txt
```

Shadowsocks — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/shadowsocks.txt
```

Shadowsocks — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/shadowsocks-base64.txt
```

Hysteria — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria.txt
```

Hysteria — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria-base64.txt
```

Hysteria2 — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria2.txt
```

Hysteria2 — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria2-base64.txt
```

SOCKS4 — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks4.txt
```

SOCKS4 — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks4-base64.txt
```

SOCKS5 — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks5.txt
```

SOCKS5 — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks5-base64.txt
```

HTTP — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/http.txt
```

HTTP — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/http-base64.txt
```

HTTPS — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/https.txt
```

HTTPS — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/https-base64.txt
```

## 🌍 Proxies by Country

<br/>

🦋 **Click here to get proxies from a specific country** 👉 [🌍 Available Countries](./output/countries/README.md)

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
- 🇦🇹 Austria
- 🇦🇺 [Australia](./output/countries/AU/)
- 🇦🇼 Aruba
- 🇦🇽 Aland Islands
- 🇦🇿 Azerbaijan
- 🇧🇦 Bosnia and Herzegovina
- 🇧🇧 Barbados
- 🇧🇩 Bangladesh
- 🇧🇪 Belgium
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
- 🇨🇳 [China](./output/countries/CN/)
- 🇨🇴 Colombia
- 🇨🇷 Costa Rica
- 🇨🇺 Cuba
- 🇨🇻 Cabo Verde
- 🇨🇼 Curacao
- 🇨🇽 Christmas Island
- 🇨🇾 Cyprus
- 🇨🇿 [Czechia](./output/countries/CZ/)
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
- 🇪🇸 Spain
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
- 🇬🇷 [Greece](./output/countries/GR/)
- 🇬🇸 South Georgia and the South Sandwich Islands
- 🇬🇹 Guatemala
- 🇬🇺 Guam
- 🇬🇼 Guinea-Bissau
- 🇬🇾 Guyana
- 🇭🇰 [Hong Kong](./output/countries/HK/)
- 🇭🇲 Heard Island and McDonald Islands
- 🇭🇳 Honduras
- 🇭🇷 Croatia
- 🇭🇹 Haiti
- 🇭🇺 Hungary
- 🇮🇩 Indonesia
- 🇮🇪 Ireland
- 🇮🇱 Israel
- 🇮🇲 Isle of Man
- 🇮🇳 [India](./output/countries/IN/)
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
- 🇲🇽 [Mexico](./output/countries/MX/)
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
- 🇵🇱 [Poland](./output/countries/PL/)
- 🇵🇲 Saint Pierre and Miquelon
- 🇵🇳 Pitcairn
- 🇵🇷 Puerto Rico
- 🇵🇸 Palestine
- 🇵🇹 Portugal
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
- 🇸🇮 [Slovenia](./output/countries/SI/)
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
- 🇹🇭 [Thailand](./output/countries/TH/)
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
- 🇺🇦 [Ukraine](./output/countries/UA/)
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

</details>

<details>
<summary>🇦🇺 Australia — 1 proxy</summary>

### 🇦🇺 Australia

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AU/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AU/all-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AU/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/AU/https-base64.txt
```

</details>

<details>
<summary>🇧🇬 Bulgaria — 1 proxy</summary>

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
<summary>🇨🇦 Canada — 15 proxies</summary>

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

</details>

<details>
<summary>🇨🇭 Switzerland — 1 proxy</summary>

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

</details>

<details>
<summary>🇨🇳 China — 1 proxy</summary>

### 🇨🇳 China

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CN/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CN/all-base64.txt
```

Socks5:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CN/socks5.txt
```

Socks5 Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CN/socks5-base64.txt
```

</details>

<details>
<summary>🇨🇿 Czechia — 2 proxies</summary>

### 🇨🇿 Czechia

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CZ/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CZ/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CZ/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CZ/shadowsocks-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CZ/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/CZ/https-base64.txt
```

</details>

<details>
<summary>🇩🇪 Germany — 15 proxies</summary>

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

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/https-base64.txt
```

</details>

<details>
<summary>🇪🇪 Estonia — 2 proxies</summary>

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
<summary>🇫🇷 France — 14 proxies</summary>

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
<summary>🇬🇧 United Kingdom — 77 proxies</summary>

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

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/GB/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/GB/https-base64.txt
```

</details>

<details>
<summary>🇬🇷 Greece — 1 proxy</summary>

### 🇬🇷 Greece

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/GR/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/GR/all-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/GR/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/GR/https-base64.txt
```

</details>

<details>
<summary>🇭🇰 Hong Kong — 7 proxies</summary>

### 🇭🇰 Hong Kong

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/HK/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/HK/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/HK/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/HK/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇮🇳 India — 2 proxies</summary>

### 🇮🇳 India

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IN/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IN/all-base64.txt
```

VMess:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IN/vmess.txt
```

VMess Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IN/vmess-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IN/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/IN/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇮🇷 Iran — 6 proxies</summary>

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
<summary>🇱🇹 Lithuania — 3 proxies</summary>

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
<summary>🇲🇽 Mexico — 2 proxies</summary>

### 🇲🇽 Mexico

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/MX/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/MX/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/MX/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/MX/shadowsocks-base64.txt
```

HTTPS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/MX/https.txt
```

HTTPS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/MX/https-base64.txt
```

</details>

<details>
<summary>🇳🇱 Netherlands — 25 proxies</summary>

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
<summary>🇵🇱 Poland — 1 proxy</summary>

### 🇵🇱 Poland

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PL/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PL/all-base64.txt
```

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PL/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/PL/vless-base64.txt
```

</details>

<details>
<summary>🇷🇴 Romania — 3 proxies</summary>

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
<summary>🇷🇺 Russia — 1 proxy</summary>

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
<summary>🇸🇨 Seychelles — 1 proxy</summary>

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
<summary>🇸🇬 Singapore — 3 proxies</summary>

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

</details>

<details>
<summary>🇸🇮 Slovenia — 1 proxy</summary>

### 🇸🇮 Slovenia

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SI/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SI/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SI/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/SI/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇹🇭 Thailand — 1 proxy</summary>

### 🇹🇭 Thailand

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/TH/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/TH/all-base64.txt
```

VLESS:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/TH/vless.txt
```

VLESS Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/TH/vless-base64.txt
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
<summary>🇺🇦 Ukraine — 1 proxy</summary>

### 🇺🇦 Ukraine

All protocols:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/UA/all.txt
```

Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/UA/all-base64.txt
```

Shadowsocks:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/UA/shadowsocks.txt
```

Shadowsocks Base64:

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/UA/shadowsocks-base64.txt
```

</details>

<details>
<summary>🇺🇸 United States — 195 proxies</summary>

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

## Quick Start

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

## License

MIT