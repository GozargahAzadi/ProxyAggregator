"""Aggregate pipeline — end-to-end orchestration."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from .models import ConfigItem, Protocol, RunSummary, SourceResult
from .parsers import extract_valid_lines, parse_config
from .sources import fetch_source, classify_source
from .dedup import deduplicate, dedup_stats, group_by_protocol, filter_by_categories
from .verification import run_verification_round, merge_round_results
from .ranking import rank_by_latency, compute_statistics
from .exporters import (
    write_txt, write_base64_txt, write_json_index,
    write_health_json, write_state_json, write_top100,
)

# ── Source definitions (extend this list) ──────────────────────────────────

LIGHT_SOURCES = [
    "https://raw.githubusercontent.com/iampedii/whitedns-sub/main/base64.txt",
    "https://raw.githubusercontent.com/4n0nymou3/multi-proxy-config-fetcher/refs/heads/main/configs/proxy_configs.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/v2rayNG-Config/main/server.txt",
]

HEAVY_SOURCES = [
    "https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/V2RAY_RAW.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/All_Configs_Sub.txt",
]


def all_sources() -> List[str]:
    """Return all source URLs (LIGHT + HEAVY, no duplicates)."""
    seen: set = set()
    out: List[str] = []
    for url in LIGHT_SOURCES + HEAVY_SOURCES:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


# ── Main pipeline ───────────────────────────────────────────────────────────

def run(out_dir: str = ".", *,
        force: bool = False,
        dry_run: bool = False) -> RunSummary:
    """Execute the full aggregation pipeline.

    Args:
        out_dir: Directory to write output files.
        force: Ignore freshness gate.
        dry_run: Don't write files, just return summary.
    """
    start_time = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")
    now_unix = now.timestamp()

    summary = RunSummary(started_at=start_time)

    # ── Phase 1: Fetch sources ────────────────────────────────────────────
    print(f"[{now_str}] Phase 1: Fetching sources...")
    sources = all_sources()
    fetch_results: List[SourceResult] = []

    def _fetch_one(url: str) -> SourceResult:
        t0 = time.monotonic()
        text, code, err = fetch_source(url)
        duration = time.monotonic() - t0
        src = classify_source(url, text, code, err)
        src.duration_sec = round(duration, 2)
        # Parse configs from fetched text
        if src.status == "ok":
            lines = extract_valid_lines(text)
            parsed = [parse_config(line) for line in lines]
            valid = [p for p in parsed if p is not None]
            src.config_count = len(valid)
        return src

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_one, url): url for url in sources}
        for future in as_completed(futures):
            try:
                result = future.result()
                fetch_results.append(result)
                print(f"  [{result.status}] {result.url[:60]}... "
                      f"(count={result.config_count}, {result.duration_sec:.1f}s)")
            except Exception as exc:
                url = futures[future]
                fetch_results.append(SourceResult(url=url, status="fail",
                                                   error=str(exc)))

    summary.sources = fetch_results
    summary.total_configs = sum(r.config_count for r in fetch_results if r.status == "ok")

    # ── Phase 2: Parse & deduplicate ──────────────────────────────────────
    print(f"[{now_str}] Phase 2: Parsing and deduplicating...")
    all_configs: List[ConfigItem] = []
    broken_count = 0

    for src in fetch_results:
        if src.status != "ok":
            continue
        # Re-fetch text to parse (we only counted in classify_source)
        text, code, err = fetch_source(src.url)
        lines = extract_valid_lines(text)
        for line in lines:
            cfg = parse_config(line)
            if cfg:
                all_configs.append(cfg)
            else:
                broken_count += 1

    orig_count = len(all_configs)
    deduped = deduplicate(all_configs)
    dup_stats = dedup_stats(all_configs, deduped)
    summary.unique_configs = len(deduped)
    summary.duplicates_removed = dup_stats["duplicates_removed"]
    summary.broken_removed = broken_count

    print(f"  Raw: {orig_count} → Unique: {len(deduped)} "
          f"(removed {dup_stats['duplicates_removed']} dupes, {broken_count} broken)")

    # ── Phase 3: Verification (L2+L3) ─────────────────────────────────────
    print(f"[{now_str}] Phase 3: Verification ({'dry run' if dry_run else 'live'})...")
    if not dry_run:
        round_results = []
        for rnd in range(1, 4):  # 3 rounds
            print(f"  Round {rnd}/3...")
            rnd_result = run_verification_round(deduped, round_num=rnd)
            round_results.append(rnd_result)
            print(f"    OK: {rnd_result['stats']['ok']}/"
                  f"{rnd_result['stats']['total']}")

        verified, verif_stats = merge_round_results(deduped, round_results)
    else:
        # In dry run, mark all as passed for testing
        verified = deduped[:]
        for cfg in verified:
            object.__setattr__(cfg, "verified_rounds", 3)
            object.__setattr__(cfg, "total_rounds", 3)
            object.__setattr__(cfg, "median_latency_ms", 100.0)  # synthetic
        verif_stats = {"rounds": 3, "ever_ok": len(verified),
                       "stable": len(verified), "per_round_ok": [len(verified)] * 3}

    summary.verified_count = len(verified)
    print(f"  Verified: {len(verified)}/{len(deduped)}")

    # ── Phase 4: Categorize & rank ────────────────────────────────────────
    print(f"[{now_str}] Phase 4: Categorizing and ranking...")
    buckets = filter_by_categories(deduped)
    top100 = rank_by_latency(verified, top_n=100)
    lat_stats = compute_statistics(verified)

    summary.fast_count = len(buckets.get("fast", []))
    summary.secure_count = len(buckets.get("secure", []))
    summary.top_count = len(top100)

    print(f"  Verified: {len(buckets['verified'])}, "
          f"Fast: {len(buckets['fast'])}, "
          f"Secure: {len(buckets['secure'])}, "
          f"Top100: {len(top100)}")

    # ── Phase 5: Export ───────────────────────────────────────────────────
    if not dry_run:
        print(f"[{now_str}] Phase 5: Exporting...")
        _export_all(out_dir, deduped, buckets, top100, lat_stats)

    elapsed = time.monotonic() - start_time
    summary.elapsed_sec = round(elapsed, 2)
    summary.cascade = verif_stats

    # Update timestamps
    timestamps = {
        "updated_at": now_str,
        "updated_at_unix": now_unix,
        "next_update_eta": _calc_eta(),
    }

    if not dry_run:
        write_json_index(
            os.path.join(out_dir, "index.json"),
            {
                "sources_ok": sum(1 for s in fetch_results if s.status == "ok"),
                "sources_fail": sum(1 for s in fetch_results if s.status == "fail"),
                "sources_empty": sum(1 for s in fetch_results if s.status == "empty"),
            },
            buckets,
            _count_protocols(deduped),
            timestamps,
        )
        write_health_json(
            os.path.join(out_dir, "health.json"),
            {
                "run": summary.to_dict(),
                "cascade": verif_stats,
                "latency_stats": lat_stats,
            },
        )

    print(f"[{now_str}] Done in {elapsed:.1f}s")
    return summary


def _export_all(out_dir: str, all_configs: List[ConfigItem],
                buckets: Dict[str, List[ConfigItem]],
                top100: List[ConfigItem],
                lat_stats: dict) -> None:
    """Write all output files."""
    # Text and base64 for each category
    for cat_name, cat_configs in buckets.items():
        cat_dir = os.path.join(out_dir, cat_name)
        if cat_configs:
            write_txt(os.path.join(cat_dir, "configs.txt"), cat_configs)
            write_base64_txt(os.path.join(cat_dir, "configs_base64.txt"), cat_configs)

    # Top 100
    write_top100(os.path.join(out_dir, "top100.txt"), top100)

    # Protocol-specific feeds
    proto_groups = group_by_protocol(all_configs)
    proto_dir = os.path.join(out_dir, "protocols")
    os.makedirs(proto_dir, exist_ok=True)
    for proto, proto_configs in proto_groups.items():
        if proto_configs:
            write_txt(os.path.join(proto_dir, f"{proto}.txt"), proto_configs)
            write_base64_txt(os.path.join(proto_dir, f"{proto}_base64.txt"),
                             proto_configs)

    # State
    write_state_json(os.path.join(out_dir, "state.json"), {
        "last_run": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_unique": len(all_configs),
        "verified": len(buckets.get("verified", [])),
    })


def _count_protocols(configs: List[ConfigItem]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for cfg in configs:
        proto = cfg.protocol.value
        counts[proto] = counts.get(proto, 0) + 1
    return counts


def _calc_eta() -> str:
    """Calculate next update ETA (every 15 minutes)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    next_15 = (now.minute // 15 + 1) * 15
    if next_15 >= 60:
        next_15 = 0
        now += datetime.timedelta(hours=1)
    eta = now.replace(minute=next_15, second=0, microsecond=0)
    return eta.strftime("%H:%M UTC")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ProxyAggregator — aggregate public proxy configs")
    parser.add_argument("--out", default=".", help="Output directory")
    parser.add_argument("--force", action="store_true", help="Ignore freshness gate")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing files")
    args = parser.parse_args(argv)

    summary = run(out_dir=args.out, force=args.force, dry_run=args.dry_run)
    print(f"\n=== Summary ===")
    print(f"Total unique: {summary.unique_configs}")
    print(f"Verified: {summary.verified_count}")
    print(f"Fast: {summary.fast_count}")
    print(f"Top100: {summary.top_count}")
    print(f"Elapsed: {summary.elapsed_sec:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
