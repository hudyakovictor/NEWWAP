"""
Crash-safe wrapper around the user's `core/runner_hpe.py` pose pipeline.

Adds two things on top of the original:
  * incremental JSON writes (every 25 photos) so a terminal crash never
    loses the whole pass;
  * `--resume` flag — if the output JSON already exists, load it and skip
    files already present.

The actual face detection and head-pose model are imported from
`core/head-pose-estimation`, exactly as runner_hpe.py does. No code under
`core/` is modified.

Usage:
    python poses_hpe_safe.py --input_dir <dir> --output_json <out.json> [--resume]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np
import torch
from torchvision import transforms

sys.path.insert(0, "/Users/victorkhudyakov/dutin/core/head-pose-estimation")
os.chdir("/Users/victorkhudyakov/dutin/core/head-pose-estimation")

from models import get_model, SCRFD  # noqa: E402
from utils.general import compute_euler_angles_from_rotation_matrices  # noqa: E402


def pre_process(image):
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    transform = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    return transform(image).unsqueeze(0)


def expand_bbox(x_min, y_min, x_max, y_max, factor=0.2):
    width = x_max - x_min
    height = y_max - y_min
    return (
        max(0, x_min - int(factor * height)),
        max(0, y_min - int(factor * width)),
        x_max + int(factor * height),
        y_max + int(factor * width),
    )


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

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    face_detector = SCRFD(model_path="./weights/det_10g.onnx")
    head_pose = get_model("mobilenetv3_large", num_classes=6, pretrained=False)
    state_dict = torch.load(
        "./weights/mobilenetv3_large.pt", map_location=device, weights_only=False
    )
    head_pose.load_state_dict(state_dict)
    head_pose.to(device)
    head_pose.eval()

    started = time.time()
    for i, fname in enumerate(pending, 1):
        img_path = os.path.join(args.input_dir, fname)
        try:
            frame = cv2.imread(img_path)
            if frame is None:
                results[fname] = None
            else:
                with torch.no_grad():
                    bboxes, _ = face_detector.detect(frame)
                    if len(bboxes) == 0:
                        results[fname] = None
                    else:
                        x_min, y_min, x_max, y_max = map(int, bboxes[0][:4])
                        x_min, y_min, x_max, y_max = expand_bbox(x_min, y_min, x_max, y_max)
                        crop = frame[y_min:y_max, x_min:x_max]
                        if crop.size == 0:
                            results[fname] = None
                        else:
                            tensor = pre_process(crop).to(device)
                            rot = head_pose(tensor)
                            euler = np.degrees(compute_euler_angles_from_rotation_matrices(rot))
                            results[fname] = {
                                "yaw": float(euler[:, 1].cpu().numpy()[0]),
                                "pitch": float(euler[:, 0].cpu().numpy()[0]),
                                "roll": float(euler[:, 2].cpu().numpy()[0]),
                            }
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
