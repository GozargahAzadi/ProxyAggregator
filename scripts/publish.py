#!/usr/bin/env python3
"""Publishing helper — rolling-squash commit to preserve O(1) history."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import List, Optional


OUTPUT_PATHS = [
    "all", "heavy", "light", "protocols", "archive",
    "index.json", "health.json", "verified", "fast", "secure",
    "top100.txt", "state.json", "Countries",
]


def is_output_path(path: str) -> bool:
    """Check if a path is an output file/directory."""
    for prefix in OUTPUT_PATHS:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result


def find_anchor(branch: str, out_mark: str, max_depth: int = 128) -> Optional[str]:
    """Find the latest non-output commit (anchor)."""
    # Fetch with limited depth
    for depth in [2, 4, 8, 16, 32, 64, 128]:
        try:
            run(["git", "fetch", "--depth", str(depth), "origin", branch])
        except subprocess.CalledProcessError:
            continue
        # Find latest commit not marked with out_mark
        try:
            log = run(["git", "log", f"--max-count={depth}",
                       "--format=%H %s", f"origin/{branch}"])
            for line in log.stdout.strip().split("\n"):
                if out_mark not in line:
                    return line.split()[0]
        except subprocess.CalledProcessError:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish aggregation outputs")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--out-mark", default="[auto-output]")
    args = parser.parse_args()

    # Check required outputs exist
    # Note: clash.yaml and singbox.json are not yet implemented — remove once converters are added
    must_exist = [
        "index.json", "health.json",
        "all/configs.txt", "all/configs_base64.txt",
    ]
    missing = [f for f in must_exist if not os.path.exists(f) or not os.path.getsize(f)]
    if missing:
        print(f"❌ Missing required outputs: {missing}", file=sys.stderr)
        return 1

    # Find anchor
    anchor = find_anchor(args.branch, args.out_mark)
    if not anchor:
        print("❌ No source anchor found", file=sys.stderr)
        return 1

    # Build new commit
    print(f"🔗 Anchor: {anchor[:8]}")

    # Stage output files
    for path in OUTPUT_PATHS:
        if os.path.exists(path):
            run(["git", "add", path])

    # Check for source regressions
    try:
        diff = run(["git", "diff", "--name-only", anchor, "HEAD"])
        changed = [p for p in diff.stdout.strip().split("\n") if p and not is_output_path(p)]
        if changed:
            print(f"⚠️ Source paths changed: {changed}", file=sys.stderr)
            print("Refusing to publish to avoid overwriting source changes.",
                  file=sys.stderr)
            return 1
    except subprocess.CalledProcessError:
        pass

    # Create commit
    import datetime
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    config_count = 0
    try:
        with open("index.json") as f:
            config_count = json.load(f).get("categories", {}).get("all", {}).get("unique", 0)
    except Exception:
        pass

    commit_msg = f"chore: update configs — {stamp} — {config_count} configs\n\n{args.out_mark}"
    run(["git", "commit", "-m", commit_msg])

    # Force push with lease
    try:
        run(["git", "push", "origin", f"HEAD:refs/heads/{args.branch}",
             "--force-with-lease"], check=True)
        print(f"✅ Published to {args.branch}")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"❌ Push failed: {exc.stderr}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
