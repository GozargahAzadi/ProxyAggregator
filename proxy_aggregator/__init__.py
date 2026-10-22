# ProxyAggregator — public proxy configuration aggregator
#
# Stands up from the reference repository (0xRadikal/Free-v2ray-Configs)
# but is an independent implementation using only the Python standard
# library so it can run anywhere — GitHub Actions, Termux, a laptop.
#
# No external packages are required. No VPS, no database server.
# GitHub Actions runs the pipeline on schedule and publishes results
# to the default branch with rolling-squash commits (O(1) history).
#
# Supported protocols (v1): VLESS, VMess, Trojan, Shadowsocks, Hysteria2
# Additional protocols added when they can be verified reliably.
