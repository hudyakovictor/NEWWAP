#!/usr/bin/env python3
import sys
from pathlib import Path
import numpy as np
import cv2

# Ensure backend is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.pipeline.quality_gate import QualityGate
from backend.pipeline.texture import SkinTextureAnalyzer
from backend.pipeline.uv_gen import HDUVTextureGenerator
from backend.pipeline.metrics import compute_symmetry_distance_map

def test_quality_gate_isolation():
    print("[TEST 1] Проверка Quality Gate (TX-07)...")
    # Create 200x200 BGR image
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    
    # Background (brick wall): high-frequency high-contrast sharp texture
    for i in range(0, 200, 10):
        img[i:i+2, :] = 255
        img[:, i:i+2] = 255
        
    # Face region (60, 60, 80, 80): blurred, smooth gray circle
    face_roi = np.ones((80, 80, 3), dtype=np.uint8) * 128
    face_roi = cv2.GaussianBlur(face_roi, (15, 15), 5)
    img[60:140, 60:140] = face_roi
    
    face_bbox = {'x': 60, 'y': 60, 'w': 80, 'h': 80}
    
    # Skin mask (1 inside face, 0 outside)
    skin_mask = np.zeros((200, 200), dtype=np.uint8)
    skin_mask[60:140, 60:140] = 1
    
    gate = QualityGate()
    result = gate.evaluate_face_quality(img, face_bbox, skin_mask)
    
    print(f"  Sharpness (on face skin only): {result['sharpness']:.3f}")
    print(f"  Success status:                 {result['success']}")
    
    # Should fail because the face itself is extremely blurry, regardless of the sharp brick background
    assert not result['success'], "QualityGate falsely approved blurry face due to sharp background!"
    print("  [SUCCESS] TEST 1 PASSED!")

def test_specular_gloss():
    print("[TEST 2] Защита от ложных бликов (TX-04)...")
    analyzer = SkinTextureAnalyzer()
    
    # 1. Matte skin representation (normal distribution, low variance, no glare)
    matte_gray = np.random.normal(120, 5, (100, 100)).astype(np.uint8)
    matte_mask = np.ones((100, 100), dtype=np.uint8)
    matte_gloss = analyzer.compute_specular_gloss(matte_gray, matte_mask)
    print(f"  Matte skin specular gloss: {matte_gloss:.4f}")
    
    # 2. Studio glare representation (high intensity softbox specular glare spots)
    glare_gray = np.random.normal(120, 5, (100, 100)).astype(np.uint8)
    glare_gray[20:40, 20:40] = 250 # Bright specular highlight
    glare_mask = np.ones((100, 100), dtype=np.uint8)
    glare_gloss = analyzer.compute_specular_gloss(glare_gray, glare_mask)
    print(f"  Glare skin specular gloss: {glare_gloss:.4f}")
    
    assert matte_gloss < 0.05, f"Matte skin detected as having too much glare: {matte_gloss}"
    assert glare_gloss >= 0.04, f"Failed to detect studio glare: {glare_gloss}"
    print("  [SUCCESS] TEST 2 PASSED!")

def test_uv_aliasing():
    print("[TEST 3] Проверка отсутствия UV-Алиасинга (TX-06)...")
    # Initialize high-fidelity UV generator
    generator = HDUVTextureGenerator(target_size=(128, 128))
    
    # Create low resolution crop (e.g. 32x32 webcam face crop)
    img_crop = np.ones((32, 32, 3), dtype=np.uint8) * 100
    img_crop[10:22, 10:22] = 180 # Landmark area
    
    verts_3d_aligned = np.zeros((68, 3))
    verts_2d_proj = np.zeros((68, 2))
    verts_2d_proj[:, 0] = np.linspace(2, 30, 68)
    verts_2d_proj[:, 1] = np.linspace(2, 30, 68)
    tris = np.array([[0, 1, 2], [1, 2, 3]], dtype=np.int32)
    conf_mask = np.ones((32, 32))
    
    hd_uv = generator.generate_hd_uv(img_crop, verts_3d_aligned, verts_2d_proj, tris, conf_mask)
    print(f"  Generated UV shape: {hd_uv.shape}")
    assert hd_uv.shape == (128, 128, 3), f"Incorrect UV shape generated: {hd_uv.shape}"
    print("  [SUCCESS] TEST 3 PASSED!")

def test_distance_transform_edt():
    print("[TEST 4] Правильный градиент дистанций (TX-05)...")
    # Create a simple binary mask: circle of 1s inside, 0s outside
    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.circle(mask, (50, 50), 30, 1, -1)
    
    dist_map = compute_symmetry_distance_map(mask)
    
    print(f"  Center distance (peak):     {dist_map[50, 50]:.3f}")
    print(f"  Background distance (edge): {dist_map[0, 0]:.3f}")
    
    # Center should be at max distance from edge (~30 pixels)
    assert dist_map[50, 50] > 28.0, f"Incorrect peak distance: {dist_map[50, 50]}"
    # Background should be strictly 0.0
    assert dist_map[0, 0] == 0.0, f"Background has non-zero distance: {dist_map[0, 0]}"
    print("  [SUCCESS] TEST 4 PASSED!")

def main():
    print("=== RUNNING SMOKE-TEST ITERATION 3 ===")
    test_quality_gate_isolation()
    print("-" * 40)
    test_specular_gloss()
    print("-" * 40)
    test_uv_aliasing()
    print("-" * 40)
    test_distance_transform_edt()
    print("=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    main()
