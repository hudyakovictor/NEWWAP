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

    def _estimate_noise(self, gray: np.ndarray) -> float:
        median = cv2.medianBlur(gray, 3)
        return float(np.mean(np.abs(gray.astype(np.float32) - median.astype(np.float32))))

    def evaluate(self, image_path: Union[str, Path], bbox: dict = None) -> Dict[str, Union[float, Dict[str, bool], str, bool]]:
        """
        Оценивает качество фото. Защищает пайплайн от падений и отсеивает 
        нерелевантные (слишком мелкие или шумные) лица.
        """
        img = cv2.imread(str(image_path))
        if img is None:
            # [FIX QG-01]: Вместо обрушения всего пайплайна возвращаем статус мягкого отказа
            return {
                "success": False,
                "is_rejected": True, 
                "reason": "INSUFFICIENT_DATA_UNREADABLE",
                "overall_score": 0.0,
                "overall_quality": 0.0,
                "sharpness_variance": 0.0,
                "blur_value": 0.0,
                "noise_level": 0.0,
            }

        h, w = img.shape[:2]
        
        # [FIX QG-04]: Проверка минимального разрешения лица. 
        # Форензика текстуры невозможна, если лицо меньше 150x150 пикселей.
        if bbox is not None:
            face_h = bbox.get("h", h)
            if face_h < 150:
                return {
                    "success": True,
                    "is_rejected": True,
                    "reason": f"FACE_TOO_SMALL_{int(face_h)}px",
                    "overall_score": 0.1,
                    "overall_quality": 0.1,
                    "sharpness_variance": 0.0,
                    "blur_value": 0.0,
                    "noise_level": 0.0,
                }

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Оценка размытия (Лапласиан)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        
        # [FIX QG-02]: Порог резкости должен быть динамическим или более реалистичным.
        # Для соцсетей Laplacian variance > 65 уже считается приемлемым.
        sharpness_score = float(np.clip(blur_score / 150.0, 0.0, 1.0))
        
        # [FIX QG-03]: Оценка шума. Шум не должен уводить quality в минус.
        noise_score = self._estimate_noise(gray)
        noise_quality = float(np.clip(1.0 - (noise_score / 25.0), 0.0, 1.0))
        
        # Итоговый скор. Шумное, но резкое фото получит сбалансированную оценку
        overall_score = float((sharpness_score * 0.7) + (noise_quality * 0.3))
        
        return {
            "success": True,
            "is_rejected": overall_score < 0.45, # Строгий форензик-порог
            "blur_value": blur_score,
            "sharpness_variance": blur_score,
            "noise_level": noise_score,
            "overall_score": overall_score,
            "overall_quality": overall_score,
        }
