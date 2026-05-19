import pickle
from pathlib import Path
from backend.core.utils import classify_pose_bucket
import json

def run():
    root = Path("/Volumes/SDCARD/storage/main")
    
    count = 0
    for subdir in root.iterdir():
        if not subdir.is_dir(): continue
        summary_path = subdir / "summary.json"
        recon_path = subdir / "reconstruction_v1.pkl"
        if not summary_path.exists() or not recon_path.exists(): continue
        
        try:
            with open(recon_path, "rb") as f:
                recon = pickle.load(f)
            
            res = recon.get("result")
            if not res: continue
            angles_deg = getattr(res, "angles_deg", None)
            
            if angles_deg is None: continue
            
            # Recompute bucket and pose
            yaw = -float(angles_deg[1])
            pitch = float(angles_deg[0])
            roll = float(angles_deg[2])
            
            bucket = classify_pose_bucket(yaw)
                
            with open(summary_path, "r") as f:
                summary = json.load(f)
                
            summary["pose"] = {
                "yaw": yaw,
                "pitch": pitch,
                "roll": roll,
                "bucket": bucket,
                "pose_source": "3DDFA_v3",
                "needs_manual_review": abs(yaw) > 45.0
            }
            summary["bucket"] = bucket
            
            with open(summary_path, "w") as f:
                json.dump(summary, f, indent=4)
                
            count += 1
        except Exception as e:
            print(f"Error on {subdir.name}: {e}")
            
    print(f"Fixed {count} summaries.")

if __name__ == "__main__":
    run()
