from backend.core.head_pose import HighResHeadPoseEstimator
from pathlib import Path

estimator = HighResHeadPoseEstimator()
image_path = "/Volumes/SDCARD/storage/main/2010_03_17_y-59p19r-18/2010_03_17_y-59p19r-18.jpg"
if not Path(image_path).exists():
    print("Test image not found, skipping specific test.")
else:
    result = estimator.predict(image_path)
    print("Result:", result)
