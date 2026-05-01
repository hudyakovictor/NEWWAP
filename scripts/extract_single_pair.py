"""
Extract a single main photo + its closest-angle calibration photo.

Usage:
    python scripts/extract_single_pair.py

Picks the most frontal main photo, finds the closest calibration photo by
angular distance, and runs the full forensic pipeline (extract_photo_bundle)
on both. Output goes to storage/main/<photo_id>/ and storage/calibration/<photo_id>/.
"""
import sys
import json
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from core.analysis import extract_photo_bundle
from core.config import SETTINGS
from core.utils import stable_photo_id, ensure_directory


def load_poses(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)


def angular_distance(a: dict, b: dict) -> float:
    dy = a.get("yaw", 0) - b.get("yaw", 0)
    dp = a.get("pitch", 0) - b.get("pitch", 0)
    dr = a.get("roll", 0) - b.get("roll", 0)
    return math.sqrt(dy * dy + dp * dp + dr * dr)


def pick_best_main(poses: dict) -> tuple[str, dict]:
    """Pick the most frontal main photo (smallest |yaw|+|pitch|)."""
    best_name = None
    best_score = 999
    best_data = None
    for name, data in poses.items():
        if data.get("source") == "none":
            continue
        score = abs(data.get("yaw", 999)) + abs(data.get("pitch", 999))
        if score < best_score:
            best_score = score
            best_name = name
            best_data = data
    return best_name, best_data


def find_closest_calibration(main_pose: dict, calibration_poses: dict) -> tuple[str, dict]:
    """Find the calibration photo with the smallest angular distance to main_pose."""
    best_name = None
    best_dist = 999
    best_data = None
    for name, data in calibration_poses.items():
        if data.get("source") == "none":
            continue
        dist = angular_distance(main_pose, data)
        if dist < best_dist:
            best_dist = dist
            best_name = name
            best_data = data
    return best_name, best_data


def main():
    # Load pose data
    main_poses = load_poses(REPO_ROOT / "storage" / "poses" / "poses_main_consolidated.json")
    calibration_poses = load_poses(REPO_ROOT / "storage" / "poses" / "poses_myface_consolidated.json")

    if not main_poses:
        print("ERROR: No main pose data found")
        sys.exit(1)
    if not calibration_poses:
        print("ERROR: No calibration pose data found")
        sys.exit(1)

    # Pick the most frontal main photo
    main_name, main_pose = pick_best_main(main_poses)
    print(f"Selected main photo: {main_name}")
    print(f"  yaw={main_pose['yaw']:.1f} pitch={main_pose['pitch']:.1f} roll={main_pose['roll']:.1f}")

    # Find closest calibration photo
    calibration_name, calibration_pose = find_closest_calibration(main_pose, calibration_poses)
    print(f"Selected calibration photo: {calibration_name}")
    print(f"  yaw={calibration_pose['yaw']:.1f} pitch={calibration_pose['pitch']:.1f} roll={calibration_pose['roll']:.1f}")
    dist = angular_distance(main_pose, calibration_pose)
    print(f"  Angular distance: {dist:.2f}°")

    # Resolve actual file paths
    main_path = SETTINGS.main_photos_dir / main_name
    calibration_path = SETTINGS.calibration_dir / calibration_name

    if not main_path.exists():
        # Fallback: check ui/public/photos_main/
        main_path = REPO_ROOT / "ui" / "public" / "photos_main" / main_name
    if not calibration_path.exists():
        calibration_path = REPO_ROOT / "ui" / "public" / "photos_myface" / calibration_name

    if not main_path.exists():
        print(f"ERROR: Main photo not found: {main_path}")
        sys.exit(1)
    if not calibration_path.exists():
        print(f"ERROR: Calibration photo not found: {calibration_path}")
        sys.exit(1)

    # Generate photo IDs using the new naming convention
    main_id = stable_photo_id("main", main_path, SETTINGS.main_photos_dir)
    calibration_id = stable_photo_id("calibration", calibration_path, SETTINGS.calibration_dir)

    print(f"\nPhoto IDs:")
    print(f"  main:   {main_id}")
    print(f"  calibration: {calibration_id}")

    # Output directories
    main_output = SETTINGS.storage_root / "main" / main_id
    calibration_output = SETTINGS.storage_root / "calibration" / calibration_id

    # Run full extraction pipeline
    print(f"\n{'='*60}")
    print(f"Extracting MAIN photo: {main_name} -> {main_id}")
    print(f"{'='*60}")
    try:
        main_summary = extract_photo_bundle(
            source_path=main_path,
            dataset="main",
            photo_id=main_id,
            output_dir=main_output,
        )
        print(f"  Status: {main_summary.get('status')}")
        print(f"  Bucket: {main_summary.get('bucket')}")
        print(f"  Vertex count: {main_summary.get('reconstruction', {}).get('vertex_count')}")
        print(f"  Artifacts: {list(main_summary.get('artifacts', {}).keys())}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Extracting CALIBRATION photo: {calibration_name} -> {calibration_id}")
    print(f"{'='*60}")
    try:
        calibration_summary = extract_photo_bundle(
            source_path=calibration_path,
            dataset="calibration",
            photo_id=calibration_id,
            output_dir=calibration_output,
        )
        print(f"  Status: {calibration_summary.get('status')}")
        print(f"  Bucket: {calibration_summary.get('bucket')}")
        print(f"  Vertex count: {calibration_summary.get('reconstruction', {}).get('vertex_count')}")
        print(f"  Artifacts: {list(calibration_summary.get('artifacts', {}).keys())}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

    print(f"\nDone! Check storage/main/{main_id}/ and storage/calibration/{calibration_id}/")


if __name__ == "__main__":
    main()
