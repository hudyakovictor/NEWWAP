from core.head_pose import HighResHeadPoseEstimator
estimator = HighResHeadPoseEstimator()
hr_pose = estimator.predict("/Volumes/SDCARD/photo/main/1999_01_11_y-45p-20r-13.jpg")
print(f"RAW YAW: {hr_pose['yaw']}")
