#!/usr/bin/env python3
import sys
from pathlib import Path
import numpy as np

# Ensure backend and core are in python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.pipeline.detect_pose import compute_robust_pose
from backend.pipeline.alignment import rigid_umeyama_robust
from backend.pipeline.compare import geodesic_pose_distance
from backend.pipeline.metrics import compute_procrustes_symmetry

def test_camera_robustness():
    print("[TEST 1] Проверка Камеры (G-03)...")
    # Standard 3D anthropometric landmarks model (68 points)
    world_pts_std = np.array([
        [-73.30, -0.11, -11.11], [ -72.61, -18.23,  -6.23], [ -70.47, -35.81,   0.24], [ -65.90, -52.44,   8.06],
        [-58.20, -67.24,  17.06], [ -47.45, -79.37,  26.47], [ -34.29, -88.46,  34.81], [ -19.46, -94.70,  39.71],
        [  0.00, -96.88,  40.40], [  19.46, -94.70,  39.71], [  34.29, -88.46,  34.81], [  47.45, -79.37,  26.47],
        [ 58.20, -67.24,  17.06], [  65.90, -52.44,   8.06], [  70.47, -35.81,   0.24], [  72.61, -18.23,  -6.23],
        [ 73.30,  -0.11, -11.11], [ -61.27,  22.15, -15.93], [ -53.47,  32.06, -21.43], [ -41.68,  34.87, -25.23],
        [-29.62,  31.57, -27.33], [ -18.97,  24.96, -28.03], [  18.97,  24.96, -28.03], [  29.62,  31.57, -27.33],
        [ 41.68,  34.87, -25.23], [  53.47,  32.06, -21.43], [  61.27,  22.15, -15.93], [   0.00,  12.16, -27.53],
        [  0.00,   1.56, -30.93], [   0.00,  -9.04, -33.93], [   0.00, -19.64, -36.23], [ -14.62, -26.04, -28.43],
        [ -7.31, -27.24, -30.93], [   0.00, -28.14, -31.83], [   7.31, -27.24, -30.93], [  14.62, -26.04, -28.43],
        [-43.68,  11.56, -23.13], [ -34.87,  16.27, -25.93], [ -25.07,  15.87, -25.93], [ -17.07,   9.66, -23.23],
        [-25.47,   7.56, -23.13], [ -35.27,   7.66, -22.93], [  17.07,   9.66, -23.23], [  25.07,  15.87, -25.93],
        [ 34.87,  16.27, -25.93], [  43.68,  11.56, -23.13], [  35.27,   7.66, -22.93], [  25.47,   7.56, -23.13],
        [-28.43, -48.44,  11.87], [ -15.42, -43.14, -13.03], [  -5.61, -41.54, -23.43], [   0.00, -42.24, -25.13],
        [  5.61, -41.54, -23.43], [  15.42, -43.14, -13.03], [  28.43, -48.44,  11.87], [  20.42, -56.74,  15.07],
        [ 10.21, -60.84,  17.77], [   0.00, -61.54,  18.47], [ -10.21, -60.84,  17.77], [ -20.42, -56.74,  15.07],
        [-24.43, -49.04,   6.37], [ -10.21, -45.94, -13.23], [   0.00, -45.34, -16.43], [  10.21, -45.94, -13.23],
        [ 24.43, -49.04,   6.37], [  15.42, -56.24,  12.77], [   0.00, -57.54,  14.07], [ -15.42, -56.24,  12.77]
    ], dtype=np.float64)

    # Rotate 45 degrees yaw (Ry) around Y axis
    theta = np.radians(45.0)
    c, s = np.cos(theta), np.sin(theta)
    Ry = np.array([
        [c, 0, s],
        [0, 1, 0],
        [-s, 0, c]
    ], dtype=np.float64)

    # Apply rotation and standard translation
    rotated_pts = world_pts_std @ Ry.T + np.array([0, 0, 150.0]) # Shift forward in Z

    # Project using true camera matrix for 120x120 crop
    focal = 120 * (112.0 / 224.0)
    cx, cy = 60.0, 60.0
    projected = np.zeros((68, 2))
    projected[:, 0] = rotated_pts[:, 0] * focal / rotated_pts[:, 2] + cx
    projected[:, 1] = rotated_pts[:, 1] * focal / rotated_pts[:, 2] + cy

    # Run robust pose estimation on mock 120x120 landmarks
    angles_deg, _, _ = compute_robust_pose(projected, (120, 120))
    pitch, yaw, roll = angles_deg

    print(f"  Computed Pitch: {pitch:.3f}°")
    print(f"  Computed Yaw:   {yaw:.3f}°")
    print(f"  Computed Roll:  {roll:.3f}°")

    assert abs(pitch) <= 0.5, f"Pitch error too high: {pitch}°"
    print("  [SUCCESS] TEST 1 PASSED!")

def test_geodesic_distance():
    print("[TEST 2] Проверка Геодезической дистанции (M-02)...")
    # Identity rotation (frontal)
    R_frontal = np.eye(3)

    # 45 degrees yaw rotation matrix
    theta = np.radians(45.0)
    c, s = np.cos(theta), np.sin(theta)
    R_45 = np.array([
        [c, 0, s],
        [0, 1, 0],
        [-s, 0, c]
    ])

    dist = geodesic_pose_distance(R_frontal, R_45)
    print(f"  Computed Geodesic Distance: {dist:.3f}°")
    assert abs(dist - 45.0) <= 0.1, f"Geodesic distance calculation incorrect: {dist}°"
    print("  [SUCCESS] TEST 2 PASSED!")

def test_svd_singularity():
    print("[TEST 3] Проверка Сингулярности SVD (M-01)...")
    # Create coplanar / degenerate collinear points
    src = np.zeros((10, 3))
    src[:, 0] = np.linspace(-10, 10, 10) # Straight line along X axis
    dst = src.copy()

    try:
        rigid_umeyama_robust(src, dst, allow_scale=True)
        print("  [FAIL] Did not raise LinAlgError for degenerate points!")
        sys.exit(1)
    except np.linalg.LinAlgError as e:
        print(f"  [SUCCESS] Correctly caught Singularity: '{e}'")
        print("  [SUCCESS] TEST 3 PASSED!")

def test_procrustes_symmetry():
    print("[TEST 4] Проверка Симметрии (M-03)...")
    # Create synthetic symmetric texture (512, 512, 3)
    uv_texture = np.ones((512, 512, 3), dtype=np.uint8) * 128
    
    # Left and right landmarks (perfectly symmetrical)
    lm_left = np.array([[100, 200], [150, 300]], dtype=np.float64)
    lm_right = np.array([[100, 200], [150, 300]], dtype=np.float64) # Perfectly symmetrical coordinates
    
    conf_mask = np.zeros((512, 512))
    conf_mask[150:350, 150:362] = 1.0

    score = compute_procrustes_symmetry(uv_texture, lm_left, lm_right, conf_mask)
    print(f"  Computed Symmetry Score: {score:.4f}")
    assert score >= 0.98, f"Symmetry score too low: {score}"
    print("  [SUCCESS] TEST 4 PASSED!")

def main():
    print("=== RUNNING SMOKE-TEST ITERATION 2 ===")
    test_camera_robustness()
    print("-" * 40)
    test_geodesic_distance()
    print("-" * 40)
    test_svd_singularity()
    print("-" * 40)
    test_procrustes_symmetry()
    print("=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    main()
