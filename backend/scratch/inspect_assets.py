import numpy as np
from pathlib import Path

assets_path = Path("/Users/victorkhudyakov/dutin/core/3ddfa_v3/assets/face_model.npy")
data = np.load(assets_path, allow_pickle=True).item()
print("Keys:", data.keys())
if 'annotation' in data:
    ann = data['annotation']
    print("Annotation shape:", ann.shape)
    # The order usually matches BASE_ZONE_NAMES
    # ('right_eye', 'left_eye', 'right_eyebrow', 'left_eyebrow', 'nose', 'upper_lip', 'lower_lip', 'skin')

