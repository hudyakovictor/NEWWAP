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

    def evaluate_face_quality(self, img_full: np.ndarray, face_bbox: dict, skin_mask: np.ndarray) -> dict:
        """
        Оценивает качество СТРОГО внутри Bounding Box и маски кожи.
        Исправляет баг оценки качества по заднему фону (TX-07).
        """
        x, y, w, h = face_bbox['x'], face_bbox['y'], face_bbox['w'], face_bbox['h']
        
        # 1. Защита от микро-лиц (Баг: слишком маленькие лица проходили проверку)
        if w < 60 or h < 60:
            return {"success": False, "reason": "FACE_TOO_SMALL", "sharpness": 0.0}
            
        # 2. Вырезаем только лицо
        face_crop = img_full[y:y+h, x:x+w]
        
        # Если маска кожи передана, применяем ее, чтобы исключить волосы и очки
        if skin_mask is not None:
            # Убедимся, что маска совпадает по размеру с кропом
            mask_crop = skin_mask[y:y+h, x:x+w]
            gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            
            # 3. Измерение резкости (Variance of Laplacian) только по коже
            # Пиксели вне маски не должны влиять на дисперсию
            laplacian = cv2.Laplacian(gray_crop, cv2.CV_64F)
            valid_laplacian = laplacian[mask_crop > 0]
            
            if len(valid_laplacian) < 100:
                return {"success": False, "reason": "INSUFFICIENT_SKIN", "sharpness": 0.0}
                
            sharpness = np.var(valid_laplacian)
        else:
            gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            sharpness = cv2.Laplacian(gray_crop, cv2.CV_64F).var()

        # 4. Оценка шума (Median Blur разница)
        median_blurred = cv2.medianBlur(gray_crop, 3)
        noise_diff = np.abs(gray_crop.astype(np.int16) - median_blurred.astype(np.int16))
        noise_level = np.mean(noise_diff[mask_crop > 0]) if skin_mask is not None else np.mean(noise_diff)

        success = (sharpness > (self.blur_threshold if hasattr(self, 'blur_threshold') else 150.0)) and (noise_level < (self.noise_threshold if hasattr(self, 'noise_threshold') else 25.0))
        
        return {
            "success": success,
            "sharpness": float(sharpness),
            "noise_level": float(noise_level),
            "overall_score": float(np.clip(sharpness / 400.0, 0, 1.0)) # Нормализация
        }
