import re
import os
import logging
from pathlib import Path
from backend.core.head_pose import HighResHeadPoseEstimator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def fix_filenames_in_dir(directory: Path):
    if not directory.exists():
        logging.warning(f"Directory {directory} does not exist.")
        return
        
    estimator = HighResHeadPoseEstimator()
    photos = list(directory.glob("*.jpg")) + list(directory.glob("*.png")) + list(directory.glob("*.jpeg"))
    
    # Filter out hidden macOS files
    photos = [p for p in photos if not p.name.startswith("._")]
    
    renamed_count = 0
    for idx, photo_path in enumerate(photos):
        filename = photo_path.name
        
        match = re.search(r'_y(-?\d+)', filename)
        if not match:
            continue
            
        old_yaw_str = match.group(1)
        old_yaw = int(old_yaw_str)
        
        try:
            hr_pose = estimator.predict(photo_path)
            if not hr_pose:
                continue
                
            yaw_corrected = -hr_pose["yaw"]
            
            needs_minus = (yaw_corrected < -5.0)  # Add a small buffer to avoid flipping 0 degrees
            needs_plus = (yaw_corrected > 5.0)
            
            has_minus = (old_yaw < 0)
            
            new_filename = None
            if needs_minus and not has_minus:
                # Add minus
                new_yaw_str = f"-{old_yaw_str}"
                new_filename = filename.replace(f"_y{old_yaw_str}", f"_y{new_yaw_str}")
            elif needs_plus and has_minus:
                # Remove minus
                new_yaw_str = old_yaw_str.replace("-", "")
                new_filename = filename.replace(f"_y{old_yaw_str}", f"_y{new_yaw_str}")
                
            if new_filename:
                os.rename(photo_path, photo_path.parent / new_filename)
                logging.info(f"Fixed: {filename} -> {new_filename} (AI yaw: {yaw_corrected:.1f})")
                renamed_count += 1
                
        except Exception as e:
            logging.error(f"Error processing {filename}: {e}")
            
    logging.info(f"Finished {directory.name}: renamed {renamed_count} files.")

def run():
    fix_filenames_in_dir(Path("/Volumes/SDCARD/photo/main"))
    fix_filenames_in_dir(Path("/Volumes/SDCARD/photo/calibration"))

if __name__ == "__main__":
    run()
