"""
Merge primary (HPE) and fallback (3DDFA) pose outputs into a single
consolidated JSON per folder.

For every photo:
    - if HPE produced a pose, take HPE and tag source="hpe"
    - else if 3DDFA produced a pose, take 3DDFA and tag source="3ddfa"
    - else tag source="none" with null pose

Also classifies each pose into one of:
    frontal, three_quarter_left, three_quarter_right,
    profile_left, profile_right
using yaw thresholds that match the rest of the project.

Writes:
    poses_<folder>_consolidated.json
    poses_<folder>_summary.json   (counts per bucket + per source)

Usage:
    python poses_merge.py --primary <hpe.json> --fallback <3ddfa.json> --label main
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter

POSES = ("frontal", "three_quarter_left", "three_quarter_right",
         "profile_left", "profile_right")


def classify(yaw: float) -> str:
    if abs(yaw) < 10:
        return "frontal"
    if yaw < -50:
        return "profile_left"
    if yaw > 50:
        return "profile_right"
    return "three_quarter_left" if yaw < 0 else "three_quarter_right"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--primary", required=True, help="HPE output JSON")
    p.add_argument("--fallback", required=True, help="3DDFA output JSON")
    p.add_argument("--label", required=True, help="output basename, e.g. main")
    p.add_argument("--out_dir", default="/Users/victorkhudyakov/dutin/newapp/storage/poses")
    args = p.parse_args()

    primary = json.load(open(args.primary))
    fallback = json.load(open(args.fallback)) if os.path.exists(args.fallback) else {}

    consolidated: dict[str, dict] = {}
    src_counter = Counter()
    bucket_counter: dict[str, Counter] = {p: Counter() for p in POSES}
    bucket_counter["none"] = Counter()
    overall_buckets: Counter = Counter()

    for fname, p_pose in primary.items():
        if p_pose is not None:
            entry = {**p_pose, "source": "hpe"}
        else:
            f_pose = fallback.get(fname)
            if f_pose is not None:
                entry = {**f_pose, "source": "3ddfa"}
            else:
                entry = {"yaw": None, "pitch": None, "roll": None, "source": "none"}
        if entry["yaw"] is not None:
            entry["classification"] = classify(entry["yaw"])
        else:
            entry["classification"] = "none"
        consolidated[fname] = entry
        src_counter[entry["source"]] += 1
        overall_buckets[entry["classification"]] += 1
        bucket_counter[entry["classification"]][entry["source"]] += 1

    out_path = os.path.join(args.out_dir, f"poses_{args.label}_consolidated.json")
    with open(out_path, "w") as f:
        json.dump(consolidated, f)

    summary = {
        "total": len(consolidated),
        "by_source": dict(src_counter),
        "by_bucket": dict(overall_buckets),
        "by_bucket_and_source": {b: dict(c) for b, c in bucket_counter.items()},
    }
    summary_path = os.path.join(args.out_dir, f"poses_{args.label}_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n[{args.label}] total {summary['total']}")
    for src, n in src_counter.most_common():
        print(f"  source: {src:8s} {n:5d}")
    print("  bucket:")
    for b in (*POSES, "none"):
        n = overall_buckets.get(b, 0)
        if n:
            srcs = bucket_counter[b]
            src_str = ", ".join(f"{s}={c}" for s, c in srcs.items())
            print(f"    {b:25s} {n:5d}  ({src_str})")
    print(f"  written: {out_path}")
    print(f"  summary: {summary_path}")


if __name__ == "__main__":
    main()
