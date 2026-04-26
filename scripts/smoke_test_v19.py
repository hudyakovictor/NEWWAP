import sys
import os
import json
from pathlib import Path

# Add backend and core to path
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT / "backend"))
sys.path.append(str(ROOT))

import cv2
import numpy as np
from pipeline.cascade import CascadeEngine
from pipeline.reconstruction import ReconstructionAdapter

def run_smoke_test():
    print("🚀 Starting DEEPUTIN Forensic Pipeline Smoke Test...")
    
    # 1. Setup
    photo_path = ROOT / "ui" / "public" / "photos_main" / "1999_08_16.jpg"
    if not photo_path.exists():
        print(f"❌ Sample photo not found at {photo_path}")
        return
    
    output_base = ROOT / "storage" / "smoke_test"
    output_base.mkdir(parents=True, exist_ok=True)
    
    print(f"📸 Input: {photo_path.name}")
    
    # 2. Initialize Engine
    print("⚙️  Initializing CascadeEngine...")
    engine = CascadeEngine()
    
    # 3. Process Photo
    print("🧠 Processing full pipeline (Extraction + Forensics)...")
    try:
        # We simulate the service's extraction logic
        photo_id = "smoke-1999-08-16"
        entry_dir = output_base / photo_id
        entry_dir.mkdir(parents=True, exist_ok=True)
        
        bundle = engine.analyze_single(Path(photo_path))
        
        # 4. Verify Metrics
        print("\n📊 Verification of Metrics:")
        texture = bundle.get("texture", {})
        quality = bundle.get("quality", {})
        
        required_texture = [
            "pore_density_raw",
            "wrinkle_depth_raw",
            "silicone_probability",
            "lbp_complexity",
        ]
        required_quality = [
            "blur_laplacian",
            "sharpness_tenengrad",
            "jpeg_blockiness"
        ]
        
        all_ok = True
        for key in required_texture:
            val = texture.get(key)
            status = "✅" if val is not None else "❌"
            print(f"  {status} texture.{key}: {val}")
            if val is None: all_ok = False

        for key in required_quality:
            val = quality.get(key)
            status = "✅" if val is not None else "❌"
            print(f"  {status} quality.{key}: {val}")
            if val is None: all_ok = False
        
        # 5. Verify Artifacts
        print("\n🖼️  Verification of Artifacts:")
        artifacts = bundle.get("artifacts", {})
        artifact_keys = ["uv_texture", "uv_confidence", "uv_mask"]
        
        for key in artifact_keys:
            filename = artifacts.get(key)
            if filename:
                fpath = entry_dir / "recon" / filename
                status = "✅" if fpath.exists() else "❌"
                print(f"  {status} {key} file: {filename} ({'exists' if fpath.exists() else 'MISSING'})")
                if not fpath.exists():
                    all_ok = False
            else:
                print(f"  ❌ {key} entry missing in artifacts")
                all_ok = False
        
        if all_ok:
            print("\n✨ SMOKE TEST PASSED! All forensic modules are correctly aligned.")
        else:
            print("\n⚠️  SMOKE TEST COMPLETED WITH WARNINGS/ERRORS.")
            
    except Exception as e:
        print(f"\n💥 CRITICAL ERROR during smoke test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_smoke_test()
