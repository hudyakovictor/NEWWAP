"""
Extract real face bounding boxes via SCRFD (the detector inside
core/head-pose-estimation). Output is a JSON keyed by filename with
{x, y, w, h, score, kp5} per file (kp5 = 5 facial keypoints).

This is a separate, lightweight pass — it doesn't compute pose, just gives
us a real per-photo face box that downstream stages (texture analysis,
crop extraction) can use.

Same crash-safety + resume contract as poses_hpe_safe.py.

Usage:
  python bbox_safe.py --input_dir <dir> --output_json <path> [--resume]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2

sys.path.insert(0, "/Users/victorkhudyakov/dutin/core/head-pose-estimation")
os.chdir("/Users/victorkhudyakov/dutin/core/head-pose-estimation")

from models import SCRFD  # noqa: E402


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--input_dir", required=True)
    cli.add_argument("--output_json", required=True)
    cli.add_argument("--resume", action="store_true")
    args = cli.parse_args()

    files = sorted(
        f for f in os.listdir(args.input_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    )
    results: dict[str, dict | None] = {}
    if args.resume and os.path.exists(args.output_json):
        with open(args.output_json) as f:
            try:
                results = json.load(f)
            except json.JSONDecodeError:
                results = {}
        print(f"[resume] loaded {sum(1 for k in results if k in set(files))} prior entries", flush=True)

    pending = [f for f in files if f not in results]
    total = len(files)
    todo = len(pending)
    print(f"[start] {total} files in {args.input_dir}, {todo} still to do", flush=True)
    if todo == 0:
        with open(args.output_json, "w") as f:
            json.dump(results, f)
        return

    detector = SCRFD(model_path="./weights/det_10g.onnx")

    started = time.time()
    for i, fname in enumerate(pending, 1):
        path = os.path.join(args.input_dir, fname)
        try:
            frame = cv2.imread(path)
            if frame is None:
                results[fname] = None
            else:
                bboxes, keypoints = detector.detect(frame)
                if len(bboxes) == 0:
                    results[fname] = None
                else:
                    bb = bboxes[0]
                    x_min, y_min, x_max, y_max, score = (
                        float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]), float(bb[4])
                    )
                    h, w = frame.shape[:2]
                    kp5 = []
                    if keypoints is not None and len(keypoints) > 0:
                        kp5 = [[float(p[0]), float(p[1])] for p in keypoints[0]]
                    results[fname] = {
                        "x":     round(x_min, 1),
                        "y":     round(y_min, 1),
                        "w":     round(x_max - x_min, 1),
                        "h":     round(y_max - y_min, 1),
                        "score": round(score, 3),
                        "kp5":   kp5,
                        "imgW":  w,
                        "imgH":  h,
                    }
        except Exception as e:
            results[fname] = None
            print(f"  [warn] {fname}: {e}", flush=True)

        if i % 50 == 0 or i == todo:
            elapsed = time.time() - started
            ok = sum(1 for v in results.values() if v is not None)
            print(
                f"  [{i}/{todo}] ok={ok} miss={len(results) - ok}  "
                f"elapsed={elapsed:.1f}s  rate={i / elapsed:.2f}/s",
                flush=True,
            )
            with open(args.output_json, "w") as f:
                json.dump(results, f)

    with open(args.output_json, "w") as f:
        json.dump(results, f)
    ok = sum(1 for v in results.values() if v is not None)
    print(f"[done] total={len(results)} ok={ok} miss={len(results) - ok}", flush=True)


if __name__ == "__main__":
    main()
