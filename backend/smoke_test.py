import os
import sys
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Mock settings if needed or ensure they load from env
os.environ["DUTIN_STORAGE_ROOT"] = "/tmp/dutin_smoke_test_storage"
os.environ["DUTIN_MAIN_PHOTOS_DIR"] = "/tmp/dutin_smoke_test_main"
os.environ["DUTIN_CALIBRATION_DIR"] = "/tmp/dutin_smoke_test_cal"

from backend.core.service import ForensicWorkbenchService
from backend.core.chronology import build_timeline
from backend.core.recommendations import build_recommendations

def run_smoke_test():
    print("--- Starting Dutin NewApp Smoke Tests ---")
    
    try:
        print("[1/4] Initializing ForensicWorkbenchService...")
        service = ForensicWorkbenchService()
        print("✅ Service initialized.")
    except Exception as e:
        print(f"❌ Service initialization failed: {e}")
        return

    try:
        print("[2/4] Testing Overview generation (empty dataset)...")
        overview = service.overview()
        print(f"✅ Overview generated. Total photos: {overview['source_photo_total']}")
    except Exception as e:
        print(f"❌ Overview generation failed: {e}")
        # Not returning here, as empty dataset might be a edge case I want to see

    try:
        print("[3/4] Testing Chronology logic with mocked data...")
        mock_records = [
            {
                "photo_id": "p1",
                "date_str": "2020-01-01",
                "bucket": "frontal",
                "metrics": {"cranial_face_index": 0.8, "texture_silicone_prob": 0.1},
                "filename": "f1.jpg"
            },
            {
                "photo_id": "p2",
                "date_str": "2020-01-10",
                "bucket": "frontal",
                "metrics": {"cranial_face_index": 0.95, "texture_silicone_prob": 0.6},
                "filename": "f2.jpg"
            }
        ]
        mock_cal = {"metrics": [], "bucket_coverage": {"frontal": 1}}
        timeline = build_timeline(mock_records, mock_cal)
        
        # Verify Identity Swap detection (days < 30, high delta)
        p2 = timeline[1]
        has_swap = any(f["type"] == "impossible_short" for f in p2.get("anomaly_flags", []))
        if has_swap:
            print("✅ Chronology: Identity Swap detected correctly.")
        else:
            print("⚠️ Chronology: Identity Swap NOT detected in mock (check logic).")
            # Let's inspect the record
            print(f"Record flags: {p2.get('anomaly_flags')}")
    except Exception as e:
        print(f"❌ Chronology test failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        print("[4/4] Testing Recommendations logic...")
        recs = build_recommendations(mock_records, mock_cal)
        print(f"✅ Recommendations generated. Count: {len(recs)}")
    except Exception as e:
        print(f"❌ Recommendations test failed: {e}")

    print("--- Smoke Tests Completed ---")

if __name__ == "__main__":
    run_smoke_test()
