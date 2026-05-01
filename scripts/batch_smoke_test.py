"""
Batch extraction smoke test — 5 photos of different poses.

Usage:
    python scripts/batch_smoke_test.py [--count 5]

Extracts N photos from the main dataset, logs per-photo timing and metrics,
and produces a summary report.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

LOG_FILE = REPO_ROOT / "logs" / "batch_smoke_test.log"
RESULTS_FILE = REPO_ROOT / "logs" / "batch_smoke_test_results.json"

_all_logs: list[dict] = []


def log(photo: str, message: str, level: str = "info", data: Any = None):
    ts = datetime.now().isoformat()
    entry = {"ts": ts, "photo": photo, "level": level, "message": message}
    if data is not None:
        entry["data"] = data
    _all_logs.append(entry)
    prefix = {"info": "  ", "ok": "✅", "warn": "⚠️", "fail": "❌", "step": "▶️"}.get(level, "  ")
    print(f"[{ts[11:19]}] {prefix} [{photo}] {message}", flush=True)


def save_results():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(_all_logs, f, indent=2, ensure_ascii=False)
    fails = [e for e in _all_logs if e["level"] == "fail"]
    warns = [e for e in _all_logs if e["level"] == "warn"]
    oks = [e for e in _all_logs if e["level"] == "ok"]
    print(f"\nResults: {len(oks)} ok, {len(warns)} warn, {len(fails)} fail")
    if fails:
        return 1
    return 0


def select_diverse_photos(photos_dir: Path, count: int) -> list[Path]:
    """Select photos from different years and hopefully different poses."""
    all_photos = sorted(photos_dir.glob("*.jpg"))
    if not all_photos:
        return []

    # Pick from different years
    by_year: dict[str, list[Path]] = {}
    for p in all_photos:
        year = p.name[:4]
        by_year.setdefault(year, []).append(p)

    selected = []
    years = sorted(by_year.keys())
    # Spread across years
    step = max(1, len(years) // count)
    for i in range(0, len(years), step):
        if len(selected) >= count:
            break
        year = years[i]
        # Pick first photo from this year
        if by_year[year]:
            selected.append(by_year[year][0])

    # Fill remaining if needed
    for p in all_photos:
        if len(selected) >= count:
            break
        if p not in selected:
            selected.append(p)

    return selected[:count]


def main():
    parser = argparse.ArgumentParser(description="Batch smoke test")
    parser.add_argument("--count", type=int, default=5, help="Number of photos to extract")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"BATCH EXTRACTION SMOKE TEST ({args.count} photos)")
    print(f"{'='*60}\n")

    from core.analysis import extract_photo_bundle
    from core.utils import stable_photo_id
    from core.config import SETTINGS

    photos_dir = SETTINGS.main_photos_dir
    if not photos_dir.exists():
        # Fallback to symlinked dir
        photos_dir = REPO_ROOT / "ui" / "public" / "photos_main"

    photos = select_diverse_photos(photos_dir, args.count)
    if not photos:
        print("No photos found!")
        return 1

    print(f"Selected {len(photos)} photos:")
    for p in photos:
        print(f"  {p.name} ({p.stat().st_size / 1024:.0f} KB)")
    print()

    results_summary = []
    total_t0 = time.monotonic()

    for i, photo_path in enumerate(photos, 1):
        photo_id = stable_photo_id("main", photo_path, SETTINGS.main_photos_dir)
        output_dir = SETTINGS.storage_root / "main" / photo_id / "smoke_test"

        label = f"{i}/{len(photos)} {photo_path.name}"
        log(label, f"Starting extraction", "step")

        t0 = time.monotonic()
        try:
            result = extract_photo_bundle(
                source_path=photo_path,
                dataset="main",
                photo_id=photo_id,
                output_dir=output_dir,
            )
            dt = time.monotonic() - t0

            # Verify
            status = result.get("status")
            bucket = result.get("bucket")
            year = result.get("year") or result.get("parsed_year")
            metrics_count = len(result.get("metrics", {}))
            reliability = result.get("metrics", {}).get("reliability_weight", 0)
            artifacts = list(result.get("artifacts", {}).keys())

            issues = []
            if status not in ("ready", "needs_review"):
                issues.append(f"unexpected status: {status}")
            if metrics_count < 20:
                issues.append(f"only {metrics_count} metrics")
            if reliability < 0.1:
                issues.append(f"very low reliability: {reliability:.3f}")

            # Check artifacts on disk
            for art_name, art_file in result.get("artifacts", {}).items():
                art_path = output_dir / art_file
                if not art_path.exists():
                    issues.append(f"missing artifact: {art_name}")

            if issues:
                for issue in issues:
                    log(label, issue, "warn")

            log(label, f"Done in {dt:.1f}s: status={status}, bucket={bucket}, year={year}, metrics={metrics_count}, reliability={reliability:.2f}", "ok", {
                "status": status, "bucket": bucket, "year": year,
                "metrics_count": metrics_count, "reliability": reliability,
                "duration_s": round(dt, 1),
            })

            results_summary.append({
                "photo": photo_path.name,
                "photo_id": photo_id,
                "status": status,
                "bucket": bucket,
                "year": year,
                "metrics_count": metrics_count,
                "reliability": reliability,
                "duration_s": round(dt, 1),
                "issues": issues,
            })

        except Exception as e:
            dt = time.monotonic() - t0
            log(label, f"FAILED in {dt:.1f}s: {e}", "fail")
            import traceback
            traceback.print_exc()
            results_summary.append({
                "photo": photo_path.name,
                "photo_id": photo_id,
                "status": "error",
                "error": str(e),
                "duration_s": round(dt, 1),
            })

    total_dt = time.monotonic() - total_t0

    # Summary
    print(f"\n{'='*60}")
    print(f"BATCH SUMMARY ({len(results_summary)} photos, {total_dt:.1f}s total)")
    print(f"{'='*60}")
    for r in results_summary:
        status = r.get("status", "?")
        bucket = r.get("bucket", "?")
        dur = r.get("duration_s", 0)
        rel = r.get("reliability", 0)
        issues = r.get("issues", [])
        issue_str = f" ⚠ {', '.join(issues)}" if issues else ""
        print(f"  {r['photo']}: {status} | {bucket} | {dur:.1f}s | rel={rel:.2f}{issue_str}")

    # Write summary
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total_photos": len(results_summary),
            "total_duration_s": round(total_dt, 1),
            "avg_duration_s": round(total_dt / max(len(results_summary), 1), 1),
            "results": results_summary,
        }, f, indent=2, ensure_ascii=False)

    return save_results()


if __name__ == "__main__":
    sys.exit(main())
