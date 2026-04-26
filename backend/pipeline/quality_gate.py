from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Union

from .constants import BLUR_THRESHOLD_DEFAULT, NOISE_THRESHOLD_DEFAULT

class QualityGate:
    """
    [QUAL-01] Technical Quality Gate.
    Ensures input imagery meets forensic standards for sharpness and SNR.
    """
    def __init__(
        self, 
        blur_threshold: float = BLUR_THRESHOLD_DEFAULT, 
        noise_threshold: float = NOISE_THRESHOLD_DEFAULT
    ):
        self.blur_threshold = float(blur_threshold)
        self.noise_threshold = float(noise_threshold)

    def evaluate(self, image_path: Union[str, Path]) -> Dict[str, Union[float, Dict[str, bool]]]:
        """
        Calculates Laplacian variance (sharpness) and median absolute deviation (noise).
        """
        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"CRITICAL: Failed to read image for quality analysis: {image_path}")

        # Sharpness: variance of Laplacian
        blur_score = float(cv2.Laplacian(img, cv2.CV_64F).var())
        
        # Noise: deviation from median filtered version
        median = cv2.medianBlur(img, 3)
        noise_score = float(np.mean(np.abs(img.astype(np.float32) - median.astype(np.float32))))
        
        is_texture_rejected = blur_score < self.blur_threshold or noise_score > self.noise_threshold

        return {
            "sharpness_variance": blur_score,
            "noise_level": noise_score,
            "is_rejected": is_texture_rejected,
            "flags": {
                "REJECTED_BLUR": blur_score < self.blur_threshold,
                "REJECTED_NOISE": noise_score > self.noise_threshold,
            }
        }
