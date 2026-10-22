"""Exporters — write configs to various output formats."""
from __future__ import annotations

import base64
import json
import os
from typing import Dict, List, Optional

from .models import ConfigItem


# ── Hiddify-compatible subscription header ─────────────────────────────────

HIDDIFY_HEADER = (
    "#profile-title: ProxyAggregator\n"
    "#profile-update-interval: 1\n"
    "#subscription-userinfo: upload=0; download=0; total=0; expire=0\n"
    "#support-url: https://github.com/user/proxy-aggregator\n"
    "#profile-web-page-url: https://github.com/user/proxy-aggregator\n"
)


def write_txt(path: str, configs: List[ConfigItem]) -> None:
    """Write plain-text config list."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for cfg in configs:
            f.write(cfg.link + "\n")


def write_base64_txt(path: str, configs: List[ConfigItem]) -> None:
    """Write base64-encoded subscription with Hiddify header."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    content = HIDDIFY_HEADER + "\n".join(cfg.link for cfg in configs)
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    with open(path, "w", encoding="ascii") as f:
        f.write(encoded + "\n")


def write_json_index(path: str, summary: dict, categories: Dict[str, List[ConfigItem]],
                     protocols: Dict[str, int], timestamps: dict,
                     path_prefix: str = "") -> None:
    """Write index.json with all metadata."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = {
        "updated_at": timestamps.get("updated_at", ""),
        "updated_at_unix": timestamps.get("updated_at_unix", 0),
        "next_update_eta": timestamps.get("next_update_eta", ""),
        "categories": {
            name: {
                "unique": len(cfgs),
                "urls": _make_urls(path_prefix, name, len(cfgs)),
            }
            for name, cfgs in categories.items()
            if cfgs  # Only publish non-empty categories
        },
        "protocols": protocols,
        "summary": summary,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _make_urls(prefix: str, category: str, count: int) -> Dict[str, str]:
    """Generate URL map for a category."""
    urls: Dict[str, str] = {}
    if count > 0:
        base = f"{prefix}/{category}"
        urls["txt"] = f"{base}/configs.txt"
        urls["base64"] = f"{base}/configs_base64.txt"
    return urls


def write_health_json(path: str, health_data: dict) -> None:
    """Write health.json with source health and cascade statistics."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(health_data, f, indent=2, ensure_ascii=False)


def write_state_json(path: str, state_data: dict) -> None:
    """Write state.json with rolling per-source yield history."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2, ensure_ascii=False)


def write_top100(path: str, configs: List[ConfigItem]) -> None:
    """Write top100.txt — fastest verified configs."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for cfg in configs:
            f.write(cfg.link + "\n")
