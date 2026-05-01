"""
Backend API smoke test — verifies all endpoints return valid data.

Usage:
    python scripts/api_smoke_test.py [--base-url http://localhost:8011]

Assumes the backend is running (./run or uvicorn backend.main:app).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = REPO_ROOT / "logs" / "api_smoke_test.log"
RESULTS_FILE = REPO_ROOT / "logs" / "api_smoke_test_results.json"

_all_logs: list[dict] = []


def log(endpoint: str, message: str, level: str = "info", data: Any = None):
    ts = datetime.now().isoformat()
    entry = {"ts": ts, "endpoint": endpoint, "level": level, "message": message}
    if data is not None:
        entry["data"] = data
    _all_logs.append(entry)
    prefix = {"info": "  ", "ok": "✅", "warn": "⚠️", "fail": "❌", "step": "▶️"}.get(level, "  ")
    print(f"[{ts[11:19]}] {prefix} [{endpoint}] {message}", flush=True)


def save_results():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(_all_logs, f, indent=2, ensure_ascii=False)
    fails = [e for e in _all_logs if e["level"] == "fail"]
    warns = [e for e in _all_logs if e["level"] == "warn"]
    oks = [e for e in _all_logs if e["level"] == "ok"]
    summary = {"ok": len(oks), "warn": len(warns), "fail": len(fails)}
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults: {len(oks)} ok, {len(warns)} warn, {len(fails)} fail")
    if fails:
        return 1
    return 0


def _fetch(base_url: str, path: str, method: str = "GET", data: bytes | None = None) -> tuple[int, Any]:
    url = f"{base_url}{path}"
    req = Request(url, method=method, data=data)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = body
            return resp.status, parsed
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = body[:200]
        return e.code, parsed
    except Exception as e:
        return 0, str(e)


def test_endpoint(base_url: str, method: str, path: str, label: str,
                  expected_status: int = 200, validation=None, body: dict | None = None):
    ep = label
    log(ep, f"Testing {method} {path}", "step")
    t0 = time.monotonic()

    data = json.dumps(body).encode() if body else None
    status, response = _fetch(base_url, path, method=method, data=data)
    dt = time.monotonic() - t0

    if status == 0:
        log(ep, f"Connection failed ({dt:.2f}s)", "fail")
        return False

    if status != expected_status:
        log(ep, f"Status {status} (expected {expected_status}) ({dt:.2f}s)", "fail",
            {"status": status, "response": str(response)[:200]})
        return False

    if validation:
        try:
            issues = validation(response)
            if issues:
                for issue in issues:
                    log(ep, issue, "warn")
            else:
                log(ep, f"OK ({dt:.2f}s)", "ok")
        except Exception as e:
            log(ep, f"Validation error: {e}", "fail")
            return False
    else:
        log(ep, f"OK ({dt:.2f}s)", "ok")

    return True


def main():
    parser = argparse.ArgumentParser(description="API smoke test")
    parser.add_argument("--base-url", type=str, default="http://localhost:8011")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    print(f"Testing API at {base_url}")
    print(f"{'='*60}\n")

    # 1. Health
    test_endpoint(base_url, "GET", "/api/health", "health",
                  validation=lambda r: [] if r.get("status") == "ok" else ["status != ok"])

    # 2. Overview
    test_endpoint(base_url, "GET", "/api/overview", "overview",
                  validation=lambda r: [] if "source_photo_total" in r else ["missing source_photo_total"])

    # 3. Photos (main)
    test_endpoint(base_url, "GET", "/api/photos/main", "photos_main",
                  validation=lambda r: (
                      [] if isinstance(r.get("items"), list) and "total" in r
                      else ["missing items/total"]
                  ))

    # 4. Photos (calibration)
    test_endpoint(base_url, "GET", "/api/photos/calibration", "photos_calib",
                  validation=lambda r: (
                      [] if isinstance(r.get("items"), list)
                      else ["missing items"]
                  ))

    # 5. Photos with filters
    test_endpoint(base_url, "GET", "/api/photos/main?pose=frontal&limit=5", "photos_filtered",
                  validation=lambda r: (
                      [] if isinstance(r.get("items"), list) and len(r["items"]) <= 5
                      else [f"items count {len(r.get('items', []))} > 5"]
                  ))

    # 6. Timeline summary
    test_endpoint(base_url, "GET", "/api/timeline-summary", "timeline",
                  validation=lambda r: [] if isinstance(r, dict) else ["not a dict"])

    # 7. Calibration summary
    test_endpoint(base_url, "GET", "/api/calibration/summary", "calibration",
                  validation=lambda r: [] if isinstance(r, dict) else ["not a dict"])

    # 8. Recommendations
    test_endpoint(base_url, "GET", "/api/recommendations", "recommendations",
                  validation=lambda r: [] if isinstance(r, list) else ["not a list"])

    # 9. Pipeline stages
    test_endpoint(base_url, "GET", "/api/pipeline/stages", "pipeline_stages",
                  validation=lambda r: [] if isinstance(r, list) else ["not a list"])

    # 10. Anomalies
    test_endpoint(base_url, "GET", "/api/anomalies", "anomalies",
                  validation=lambda r: [] if isinstance(r, list) else ["not a list"])

    # 11. Investigations
    test_endpoint(base_url, "GET", "/api/investigations", "investigations",
                  validation=lambda r: [] if isinstance(r, list) else ["not a list"])

    # 12. Diary
    test_endpoint(base_url, "GET", "/api/diary", "diary",
                  validation=lambda r: [] if isinstance(r, list) else ["not a list"])

    # 13. Cache summary
    test_endpoint(base_url, "GET", "/api/cache/summary", "cache",
                  validation=lambda r: [] if isinstance(r, dict) else ["not a dict"])

    # 14. Debug ageing
    test_endpoint(base_url, "GET", "/api/debug/ageing", "ageing",
                  validation=lambda r: [] if isinstance(r, list) else ["not a list"])

    # 15. Jobs list
    test_endpoint(base_url, "GET", "/api/jobs", "jobs",
                  validation=lambda r: [] if isinstance(r, list) else ["not a list"])

    # 16. Photos in bucket
    test_endpoint(base_url, "GET", "/api/photos-in-bucket?pose=frontal", "photos_bucket",
                  validation=lambda r: [] if isinstance(r, list) else ["not a list"])

    # 17. Photo detail (if any photos exist)
    # Get first photo ID
    _, photos_resp = _fetch(base_url, "/api/photos/main?limit=1")
    if isinstance(photos_resp, dict) and photos_resp.get("items"):
        first_id = photos_resp["items"][0].get("photo_id", "")
        if first_id:
            test_endpoint(base_url, "GET", f"/api/photo/main/{first_id}", "photo_detail",
                          validation=lambda r: (
                              [] if r.get("record") or r.get("photo_id")
                              else ["missing record/photo_id"]
                          ))

    # 18. Evidence compare (POST) — only if we have 2 photos
    if isinstance(photos_resp, dict) and photos_resp.get("items") and len(photos_resp["items"]) >= 2:
        id_a = photos_resp["items"][0].get("photo_id", "")
        id_b = photos_resp["items"][1].get("photo_id", "")
        if id_a and id_b:
            test_endpoint(base_url, "POST", "/api/evidence/compare", "evidence_compare",
                          body={"photo_id_a": id_a, "photo_id_b": id_b},
                          validation=lambda r: (
                              [] if "posteriors" in r or "verdict" in r or "error" in r
                              else ["missing posteriors/verdict"]
                          ))

    return save_results()


if __name__ == "__main__":
    sys.exit(main())
