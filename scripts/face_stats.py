"""
Per-face statistics on the bbox crop: mean/std luminance, mean RGB.
This is a small but real texture-like signal — useful for spotting
gross albedo / colour-balance shifts across years.

Inputs:
  --input_dir  the photo folder
  --bbox_json  the per-file bboxes from bbox_safe.py
  --output_json  written here

Resumes if the output already exists.
"""

from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
from PIL import Image


def crop_box(img: Image.Image, bb: dict) -> Image.Image | None:
    if not bb:
        return None
    x0 = max(0, int(bb["x"]))
    y0 = max(0, int(bb["y"]))
    x1 = min(img.width, int(bb["x"] + bb["w"]))
    y1 = min(img.height, int(bb["y"] + bb["h"]))
    if x1 <= x0 or y1 <= y0:
        return None
    return img.crop((x0, y0, x1, y1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_dir", required=True)
    ap.add_argument("--bbox_json", required=True)
    ap.add_argument("--output_json", required=True)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    bboxes = json.load(open(args.bbox_json))
    files = sorted([f for f in bboxes.keys() if bboxes[f] is not None])
    total = len(files)

    results: dict[str, dict | None] = {}
    if args.resume and os.path.exists(args.output_json):
        with open(args.output_json) as f:
            try:
                results = json.load(f)
            except json.JSONDecodeError:
                results = {}
        print(f"[resume] loaded {sum(1 for k in results if k in set(files))} prior entries", flush=True)

    pending = [f for f in files if f not in results]
    todo = len(pending)
    print(f"[start] {total} files with bbox in {args.input_dir}, {todo} still to do", flush=True)
    if todo == 0:
        with open(args.output_json, "w") as f:
            json.dump(results, f)
        return

    started = time.time()
    for i, fname in enumerate(pending, 1):
        path = os.path.join(args.input_dir, fname)
        try:
            img = Image.open(path).convert("RGB")
            crop = crop_box(img, bboxes[fname])
            if crop is None:
                results[fname] = None
                continue
            arr = np.asarray(crop, dtype=np.float32)
            # Luminance via ITU-R BT.601
            lum = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
            results[fname] = {
                "meanLum": float(round(lum.mean(), 2)),
                "stdLum":  float(round(lum.std(), 2)),
                "meanR":   float(round(arr[..., 0].mean(), 1)),
                "meanG":   float(round(arr[..., 1].mean(), 1)),
                "meanB":   float(round(arr[..., 2].mean(), 1)),
                "stdR":    float(round(arr[..., 0].std(), 1)),
                "stdG":    float(round(arr[..., 1].std(), 1)),
                "stdB":    float(round(arr[..., 2].std(), 1)),
                "cropW":   crop.width,
                "cropH":   crop.height,
            }
        except Exception as e:
            results[fname] = None
            print(f"  [warn] {fname}: {e}", flush=True)

        if i % 100 == 0 or i == todo:
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
    print(f"[done] total={len(results)} ok={ok}", flush=True)


if __name__ == "__main__":
    main()
