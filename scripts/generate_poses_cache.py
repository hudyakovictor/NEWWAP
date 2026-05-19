import json
import logging
from pathlib import Path
import time
from core.head_pose import HighResHeadPoseEstimator
from core.utils import classify_pose_bucket

logging.basicConfig(level=logging.INFO)

def run():
    source_dir = Path("/Volumes/SDCARD/photo/main")
    if not source_dir.exists():
        logging.error(f"Source path {source_dir} does not exist.")
        return

    poses_cache_dir = Path("/Users/victorkhudyakov/dutin/newapp/storage/poses")
    poses_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = poses_cache_dir / "poses_main.json"

    estimator = HighResHeadPoseEstimator()
    count = 0
    pose_report = {}
    
    photos = list(source_dir.glob("*.jpg")) + list(source_dir.glob("*.png")) + list(source_dir.glob("*.jpeg"))
    logging.info(f"Found {len(photos)} photos. Generating cache...")
    
    start_time = time.time()
    for idx, photo_path in enumerate(photos):
        try:
            hr_pose = estimator.predict(photo_path)
            if hr_pose:
                # Invert yaw to match legacy filename convention (left=negative, right=positive)
                yaw = -hr_pose["yaw"]
                pitch = hr_pose["pitch"]
                roll = hr_pose["roll"]
                bucket = classify_pose_bucket(yaw)
                
                pose_report[photo_path.name] = {
                    "yaw": yaw,
                    "pitch": pitch,
                    "roll": roll,
                    "classification": bucket,
                    "source": "mobilenetv3_large"
                }
                count += 1
            if idx % 100 == 0 and idx > 0:
                logging.info(f"Processed {idx}/{len(photos)} photos...")
        except Exception as e:
            logging.error(f"Error on {photo_path.name}: {e}")
            
    with open(cache_path, "w") as f:
        json.dump(pose_report, f, indent=4)
        
    elapsed = time.time() - start_time
    logging.info(f"Successfully generated cache for {count} photos in {elapsed:.1f}s.")
    logging.info(f"Saved to {cache_path}")

if __name__ == "__main__":
    run()
