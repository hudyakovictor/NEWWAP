import json
import logging
from pathlib import Path
from core.head_pose import HighResHeadPoseEstimator
from core.utils import classify_pose_bucket

logging.basicConfig(level=logging.INFO)

def run():
    root = Path("/Volumes/SDCARD/storage/main")
    if not root.exists():
        logging.error(f"Storage path {root} does not exist.")
        return

    estimator = HighResHeadPoseEstimator()
    count = 0
    
    for subdir in root.iterdir():
        if not subdir.is_dir():
            continue
            
        summary_path = subdir / "summary.json"
        if not summary_path.exists():
            continue
            
        # Find the source photo inside the subdirectory (or original path if known)
        # We can look for the image ending with .jpg that matches the folder name
        photo_path = subdir / f"{subdir.name}.jpg"
        if not photo_path.exists():
            continue
            
        try:
            hr_pose = estimator.predict(photo_path)
            if hr_pose:
                # Invert yaw to match legacy filename convention (left=negative, right=positive)
                yaw = -hr_pose["yaw"]
                pitch = hr_pose["pitch"]
                roll = hr_pose["roll"]
                bucket = classify_pose_bucket(yaw)
                
                with open(summary_path, "r") as f:
                    summary = json.load(f)
                    
                summary["pose"] = {
                    "yaw": yaw,
                    "pitch": pitch,
                    "roll": roll,
                    "bucket": bucket,
                    "pose_source": "mobilenetv3_large",
                    "needs_manual_review": abs(yaw) > 45.0
                }
                summary["bucket"] = bucket
                
                with open(summary_path, "w") as f:
                    json.dump(summary, f, indent=4)
                    
                count += 1
                logging.info(f"Updated {subdir.name} with new pose: yaw={yaw:.1f}, bucket={bucket}")
        except Exception as e:
            logging.error(f"Error on {subdir.name}: {e}")
            
    logging.info(f"Successfully fixed {count} summaries using HighResHeadPoseEstimator.")

if __name__ == "__main__":
    run()
