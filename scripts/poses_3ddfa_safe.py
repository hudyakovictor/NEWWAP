"""
Wrapper around the user's `core/runner_3ddfa_v3.py` that:
  1. catches SystemExit (which face_box.detector raises on no-face images,
     bypassing Exception in the original runner and killing the whole run);
  2. writes the JSON incrementally so a partial run is never lost;
  3. logs a periodic progress line so I can monitor over time.

This is the *fallback* pose estimator. We use it only on photos that
runner_hpe.py couldn't process (its `null` entries).

Usage:
    python poses_3ddfa_safe.py --input_dir <dir> --output_json <out.json>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import torch
from PIL import Image

# Mirror runner_3ddfa_v3.py setup
sys.path.insert(0, "/Users/victorkhudyakov/dutin/core/3ddfa_v3")
os.chdir("/Users/victorkhudyakov/dutin/core/3ddfa_v3")

from face_box import face_box  # noqa: E402
from model.recon import face_model  # noqa: E402


def get_args() -> argparse.Namespace:
    """Minimal arg set matching runner_3ddfa_v3.py's defaults."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cpu", type=str)
    parser.add_argument("--detector_device", default="cpu", type=str)
    parser.add_argument("--iscrop", default=True)
    parser.add_argument("--detector", default="retinaface", type=str)
    parser.add_argument("--ldm68", default=False, type=bool)
    parser.add_argument("--ldm106", default=False, type=bool)
    parser.add_argument("--ldm106_2d", default=False, type=bool)
    parser.add_argument("--ldm134", default=False, type=bool)
    parser.add_argument("--seg", default=False, type=bool)
    parser.add_argument("--seg_visible", default=False, type=bool)
    parser.add_argument("--useTex", default=False, type=bool)
    parser.add_argument("--extractTex", default=False, type=bool)
    parser.add_argument("--extractTexNew", default=False, type=bool)
    parser.add_argument("--extractTexNew_symmetry", default=False, type=bool)
    parser.add_argument("--extractTexNew_detail", default=False, type=bool)
    parser.add_argument("--extractTexNew_delight", default=False, type=bool)
    parser.add_argument("--uv_res", default=1024, type=int)
    parser.add_argument("--detail_strength", default=0.75, type=float)
    parser.add_argument("--backbone", default="resnet50", type=str)
    return parser.parse_args([])


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--input_dir", required=True)
    cli.add_argument("--output_json", required=True)
    cli.add_argument(
        "--resume",
        action="store_true",
        help="If --output_json already exists, load it and skip files already present.",
    )
    args = cli.parse_args()

    files = sorted(
        f for f in os.listdir(args.input_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    )

    # Resume support: load whatever progress is already on disk so a crashed
    # terminal doesn't cost us the full pass.
    results: dict[str, dict[str, float] | None] = {}
    if args.resume and os.path.exists(args.output_json):
        with open(args.output_json) as f:
            try:
                results = json.load(f)
            except json.JSONDecodeError:
                results = {}
        already = sum(1 for k in results if k in set(files))
        print(f"[resume] loaded {already} prior entries from {args.output_json}", flush=True)

    pending = [f for f in files if f not in results]
    total = len(files)
    todo = len(pending)
    print(f"[start] {total} files in {args.input_dir}, {todo} still to do", flush=True)
    if todo == 0:
        with open(args.output_json, "w") as f:
            json.dump(results, f)
        return

    model_args = get_args()
    recon_model = face_model(model_args)
    detector = face_box(model_args).detector

    started = time.time()
    for i, fname in enumerate(pending, 1):
        path = os.path.join(args.input_dir, fname)
        try:
            im = Image.open(path).convert("RGB")
            im.thumbnail((1024, 1024))
            try:
                trans_params, im_tensor = detector(im)
            except SystemExit:
                # face_box bails out with sys.exit when it can't find a face.
                results[fname] = None
                continue

            if im_tensor is None:
                results[fname] = None
                continue

            recon_model.input_img = im_tensor.to(model_args.device)
            with torch.no_grad():
                alpha = recon_model.net_recon(recon_model.input_img)
                alpha_dict = recon_model.split_alpha(alpha)
                angles = alpha_dict["angle"].detach().cpu().numpy()[0]
                pitch, yaw, roll = float(angles[0]), float(angles[1]), float(angles[2])
            results[fname] = {
                "yaw": yaw * 180.0 / np.pi,
                "pitch": pitch * 180.0 / np.pi,
                "roll": roll * 180.0 / np.pi,
            }
        except SystemExit:
            results[fname] = None
        except Exception as e:
            results[fname] = None
            print(f"  [warn] {fname}: {e}", flush=True)

        if i % 25 == 0 or i == todo:
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
