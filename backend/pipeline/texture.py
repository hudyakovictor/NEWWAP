from __future__ import annotations

import cv2
import numpy as np
import scipy.fftpack as fft
from pathlib import Path
from typing import Any
from skimage.feature import local_binary_pattern

from .utils import weighted_mean_abs
from core.constants import SILICONE_SIGMOID_BIAS

def _sigmoid(x: float, bias: float = SILICONE_SIGMOID_BIAS) -> float:
    return float(1.0 / (1.0 + np.exp(-(x + bias))))

def _ensure_mask(mask: np.ndarray | None, shape_hw: tuple[int, int]) -> np.ndarray:
    if mask is None:
        return np.ones(shape_hw, dtype=np.uint8) * 255
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    if mask.shape[:2] != shape_hw:
        mask = cv2.resize(mask, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_NEAREST)
    return np.asarray(mask, dtype=np.uint8)

class AlbedoColorAnalyzer:
    def __init__(self):
        self.living_skin_h_range = (0, 35)
        self.silicone_s_threshold = 40

    def analyze_skin_vitality(self, rgb_uv: np.ndarray, skin_mask: np.ndarray) -> dict[str, float | bool | str]:
        if rgb_uv is None or rgb_uv.size == 0:
            return {"vitality_score": 0.0, "status": "unavailable", "synthetic_color_ratio": 0.0}
        hsv = cv2.cvtColor(rgb_uv, cv2.COLOR_RGB2HSV)
        valid = hsv[skin_mask > 0]
        if valid.size == 0:
            return {"vitality_score": 0.0, "status": "unavailable", "synthetic_color_ratio": 0.0}
        h, s = valid[:, 0], valid[:, 1]
        dead_h = (h > self.living_skin_h_range[1]) & (h < 90)
        dead_s = s < self.silicone_s_threshold
        synthetic_ratio = float(np.sum(dead_h & dead_s) / max(len(valid), 1))
        return {
            "vitality_score": float(max(0.0, 1.0 - synthetic_ratio)),
            "status": "ok",
            "synthetic_color_ratio": synthetic_ratio,
        }

class TextureFrequencyAnalyzer:
    def __init__(self, patch_size: int = 64):
        self.patch_size = patch_size

    def analyze_periodicity(self, grayscale: np.ndarray, cx: int, cy: int) -> dict[str, float | bool | str]:
        half = self.patch_size // 2
        patch = grayscale[max(0, cy-half):min(grayscale.shape[0], cy+half), 
                          max(0, cx-half):min(grayscale.shape[1], cx+half)]
        if patch.shape != (self.patch_size, self.patch_size):
            return {"periodicity_index": 0.0, "status": "patch_error"}
        f_transform = fft.fft2(patch)
        f_shift = fft.fftshift(f_transform)
        magnitude = 20 * np.log(np.abs(f_shift) + 1e-8)
        y, x = np.ogrid[-half:half, -half:half]
        center_mask = (x**2 + y**2) <= 8**2
        high = magnitude.copy()
        high[center_mask] = 0
        non_zero = high[high > 0]
        if non_zero.size == 0:
            return {"periodicity_index": 0.0, "status": "ok"}
        hf_mean = float(np.mean(non_zero))
        hf_max = float(np.max(non_zero))
        return {"periodicity_index": float(hf_max / (hf_mean + 1e-8)), "status": "ok"}

class ImageQualityAnalyzer:
    """
    [QUAL-02] Advanced Image Quality Analysis.
    Estimates JPEG artifacts, noise, and sharpness to adjust forensic weights.
    """
    def analyze(self, image: np.ndarray) -> dict[str, float]:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
        h, w = gray.shape
        
        # 1. Laplacian variance (Sharpness)
        laplacian_var = float(np.var(cv2.Laplacian(gray, cv2.CV_64F)))
        
        # 2. JPEG Blockiness (8x8 grid detection)
        if h > 16 and w > 16:
            h_a, h_b = gray[8::8, :], gray[7::8, :]
            n_h = min(h_a.shape[0], h_b.shape[0])
            h_diff = np.abs(h_a[:n_h] - h_b[:n_h]).mean()
            
            v_a, v_b = gray[:, 8::8], gray[:, 7::8]
            n_v = min(v_a.shape[1], v_b.shape[1])
            v_diff = np.abs(v_a[:, :n_v] - v_b[:, :n_v]).mean()
            blockiness = float((h_diff + v_diff) / 2.0)
        else:
            blockiness = 0.0
            
        # 3. Noise level (Median Absolute Deviation)
        median = cv2.medianBlur(gray, 3)
        noise_level = float(np.mean(np.abs(gray.astype(np.float32) - median.astype(np.float32))))
        
        # Normalized scores (0..1)
        sharpness_score = min(1.0, laplacian_var / 500.0)
        jpeg_score = max(0.0, 1.0 - blockiness / 40.0)
        noise_score = max(0.0, 1.0 - noise_level / 10.0)
        
        quality_index = (sharpness_score * 0.4 + jpeg_score * 0.3 + noise_score * 0.3)
        
        return {
            "quality_index": float(quality_index),
            "sharpness_score": sharpness_score,
            "jpeg_score": jpeg_score,
            "noise_score": noise_score,
            "laplacian_var": laplacian_var,
            "blockiness": blockiness,
            "noise_level": noise_level
        }

class SkinTextureAnalyzer:
    def __init__(self):
        self.lbp_points = 16
        self.lbp_radius = 2
        self.albedo_analyzer = AlbedoColorAnalyzer()
        self.fft_analyzer = TextureFrequencyAnalyzer(patch_size=64)
        self.quality_analyzer = ImageQualityAnalyzer()

    def analyze_image(self, image_path: Path, mask_path: Path | None = None) -> dict[str, Any]:
        try:
            # [FIX-14] Читаем RGBA если доступно (для face_crop.png с альфа-каналом)
            bgra = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
            if bgra is None:
                return {"error": "image_read_failed"}
            
            # Если RGBA (4 канала) - используем альфа как веса маски
            if bgra.ndim == 3 and bgra.shape[2] == 4:
                alpha = bgra[:, :, 3].astype(np.float32) / 255.0
                bgr = bgra[:, :, :3]
                has_alpha_mask = True
            else:
                bgr = bgra
                alpha = None
                has_alpha_mask = False
            
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape
            
            # Analyze Quality first
            quality = self.quality_analyzer.analyze(rgb)
            
            raw_mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE) if mask_path and Path(mask_path).exists() else None
            if raw_mask is not None:
                mask = _ensure_mask(raw_mask, (h, w))
                mask_float = mask.astype(np.float32) / 255.0
            elif has_alpha_mask:
                # [FIX-14] Используем альфа-канал как взвешенную маску
                mask = (alpha > 0.1).astype(np.uint8) * 255  # Бинарная для совместимости
                mask_float = alpha
            else:
                # Auto-detect face pixels from non-black regions (for masked crops like face_crop.jpg)
                mask = np.any(rgb > 0, axis=2).astype(np.uint8) * 255
                if mask.sum() == 0:
                    mask = _ensure_mask(None, (h, w))
                mask_float = mask.astype(np.float32) / 255.0
            
            valid = mask > 0
            
            # [FIX-15] Детекция признаков студийного света и ретуши
            studio_lighting_score = self._detect_studio_lighting(rgb, mask_float)
            retouch_score = self._detect_retouching(rgb, mask_float)
            
            # Laplacian variance for sharpness/noise estimation
            laplacian_var = quality["laplacian_var"]
            
            # LBP Analysis
            lbp = local_binary_pattern(gray, self.lbp_points, self.lbp_radius, method="uniform")
            lbp_values = lbp[valid]
            hist, _ = np.histogram(lbp_values, bins=32, range=(0, self.lbp_points + 2), density=True)
            lbp_complexity = float(-np.sum(hist * np.log(hist + 1e-8)))
            lbp_uniformity = float(np.max(hist))

            # Gloss and Reflectance
            hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
            v = hsv[:, :, 2][valid].astype(np.float32)
            specular_gloss = float(np.percentile(v, 90) / 255.0) if v.size > 0 else 0.0
            
            # Spatial Metrics
            ys, xs = np.where(valid)
            cx, cy = (int(np.median(xs)), int(np.percentile(ys, 25))) if xs.size > 0 else (w // 2, h // 4)
            
            # [ITER-1.3] Normalization by Laplacian variance to avoid sharpness bias
            norm_factor = laplacian_var + 1.0
            
            # Pore Density
            patch_gray = gray[max(0, cy-32):min(h, cy+32), max(0, cx-32):min(w, cx+32)]
            pore_density = (float(cv2.Laplacian(patch_gray, cv2.CV_64F).var()) / norm_factor) if patch_gray.size > 0 else 0.0
            
            # Forehead Wrinkles
            forehead_patch = gray[max(0, cy-50):min(h, cy+50), max(0, cx-100):min(w, cx+100)]
            wrinkle_forehead = (float(np.mean(cv2.Sobel(forehead_patch, cv2.CV_64F, 1, 0, ksize=3)**2)) / norm_factor) if forehead_patch.size > 0 else 0.0
            
            # [ITER-1.3] Nasolabial Wrinkles - FIX: Use dx=1 for vertical folds
            nasolabial_cy = int(h * 0.6)
            nasolabial_patch = gray[max(0, nasolabial_cy-40):min(h, nasolabial_cy+40), max(0, cx-80):min(w, cx+80)]
            wrinkle_nasolabial = (float(np.mean(cv2.Sobel(nasolabial_patch, cv2.CV_64F, 1, 0, ksize=3)**2)) / (np.mean(nasolabial_patch) + 1.0)) if nasolabial_patch.size > 0 else 0.0

            # Reliability Weight (Combined with Quality Index)
            res_score = min(w, h) / 1024.0
            reliability_weight = float(np.clip(res_score * quality["quality_index"], 0.1, 1.0))

            # Silicone Probability
            # High lbp_uniformity = uniform texture = likely synthetic/mask
            # (1.0 - lbp_uniformity) was inverted — it flagged diverse real skin as synthetic
            score = (specular_gloss * 2.1 + lbp_uniformity * 0.8) 
            silicone_probability = _sigmoid(score, bias=SILICONE_SIGMOID_BIAS)

            # [FIX-15] Корректировка silicone_probability на основе студийного света/ретуши
            # Если высокие показатели студийного света или ретуши - понижаем synthetic_prob
            # (это артефакты обработки, а не синтетика)
            synthetic_adj = (1.0 - studio_lighting_score * 0.3) * (1.0 - retouch_score * 0.4)
            adjusted_silicone_prob = silicone_probability * synthetic_adj
            
            return {
                "lbp_complexity": lbp_complexity,
                "lbp_uniformity": lbp_uniformity,
                "specular_gloss": specular_gloss,
                "silicone_probability": adjusted_silicone_prob,
                "raw_silicone_probability": silicone_probability,  # До корректировки
                "reliability_weight": reliability_weight,
                "pore_density": pore_density,
                "wrinkle_forehead": wrinkle_forehead,
                "wrinkle_nasolabial": wrinkle_nasolabial,
                "global_smoothness": float(min(50.0, 1.0 / (lbp_complexity + 1e-6))),
                "studio_lighting_score": studio_lighting_score,  # [FIX-15]
                "retouch_score": retouch_score,  # [FIX-15]
                "quality": quality
            }
        except Exception as exc:
            return {"error": str(exc)}

    def _detect_studio_lighting(self, rgb: np.ndarray, mask_float: np.ndarray) -> float:
        """
        [FIX-15] Детекция признаков студийного освещения.
        Возвращает score [0, 1], где 1 = высокая вероятность студийного света.
        
        Признаки:
        - Резкие тени (высокий contrast ratio)
        - Specular highlights на лбу/носу
        - Равномерная освещённость фона
        """
        try:
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            
            # 1. Анализ теней - измеряем динамический диапазон
            shadow_mask = (mask_float > 0.5).astype(np.uint8)
            if shadow_mask.sum() < 100:
                return 0.0
            
            face_pixels = gray[shadow_mask > 0]
            if len(face_pixels) < 100:
                return 0.0
            
            # Студийный свет часто даёт низкий dynamic range (всё освещено равномерно)
            # ИЛИ резкий контраст (harsh shadows)
            p10, p90 = np.percentile(face_pixels, [10, 90])
            dynamic_range = (p90 - p10) / 255.0
            
            # 2. Анализ бликов (specular highlights)
            hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
            v_channel = hsv[:, :, 2].astype(np.float32) / 255.0
            
            # Взвешенный percentile для насыщенных областей
            highlight_threshold = 0.85
            highlight_mask = (v_channel > highlight_threshold) & (mask_float > 0.3)
            highlight_ratio = highlight_mask.sum() / (mask_float > 0.3).sum() if (mask_float > 0.3).sum() > 0 else 0
            
            # 3. Комбинированный score
            # Низкий dynamic range (< 0.4) + высокие блики (> 0.05) = студийный свет
            if dynamic_range < 0.35 and highlight_ratio > 0.03:
                return 0.7  # Вероятно студийный свет
            elif dynamic_range > 0.6:
                return 0.3  # Естественный свет (высокий контраст)
            else:
                return 0.5  # Неопределённо
                
        except Exception:
            return 0.0

    def _detect_retouching(self, rgb: np.ndarray, mask_float: np.ndarray) -> float:
        """
        [FIX-15] Детекция признаков ретуши/сглаживания.
        Возвращает score [0, 1], где 1 = высокая вероятность ретуши.
        
        Признаки:
        - Слишком равномерная текстура (низкая локальная вариация)
        - Отсутствие мелких деталей в определённых диапазонах
        - Паттерны сглаживания (smoothing artifacts)
        """
        try:
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            
            # 1. Анализ локальной вариации текстуры
            # Разбиваем на патчи и измеряем стандартное отклонение
            patch_size = 16
            h, w = gray.shape
            local_vars = []
            
            for y in range(0, h - patch_size, patch_size):
                for x in range(0, w - patch_size, patch_size):
                    patch_mask = mask_float[y:y+patch_size, x:x+patch_size]
                    if patch_mask.mean() > 0.5:  # Достаточно кожи в патче
                        patch = gray[y:y+patch_size, x:x+patch_size]
                        local_vars.append(np.std(patch))
            
            if len(local_vars) < 5:
                return 0.0
            
            # Ретушированные изображения имеют низкую вариацию между патчами
            var_of_vars = np.std(local_vars)
            
            # 2. Анализ границ - ретушь часто размывает края
            edges = cv2.Canny(gray, 50, 150)
            edge_density = (edges > 0).sum() / edges.size
            
            # 3. Комбинированный score
            # Низкая var_of_vars (< 3.0) + низкая edge_density (< 0.02) = ретушь
            if var_of_vars < 3.0 and edge_density < 0.02:
                return 0.75
            elif var_of_vars < 5.0 and edge_density < 0.03:
                return 0.55
            else:
                return 0.25
                
        except Exception:
            return 0.0


def analyze_texture_synthetic_prob(face_crop_path: str) -> float:
    """
    Принимает путь к обрезанному изображению лица (face_crop.jpg).
    Вычисляет вероятность того, что материал синтетический (от 0.0 до 1.0).
    Использует упрощенную оценку высокочастотных деталей (FFT-подобный подход).
    """
    try:
        # Загружаем изображение в градациях серого
        img = cv2.imread(face_crop_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return 0.5 # Неизвестно
            
        # Применяем фильтр Лапласа для выделения краев/пор (микрорельефа)
        laplacian = cv2.Laplacian(img, cv2.CV_64F)
        variance = laplacian.var()
        
        # Естественная кожа имеет высокую дисперсию Лапласиана из-за пор и морщин (высокий микрорельеф)
        # Синтетика/дипфейки часто сглажены (низкая дисперсия)
        
        # Пороги (требуют тонкой настройки на реальных данных)
        NATURAL_VAR_THRESHOLD = 500.0
        SYNTHETIC_VAR_THRESHOLD = 100.0
        
        if variance > NATURAL_VAR_THRESHOLD:
            synthetic_prob = 0.05 # Очень вероятно натуральная кожа
        elif variance < SYNTHETIC_VAR_THRESHOLD:
            synthetic_prob = 0.95 # Очень вероятно синтетика/блюр
        else:
            # Линейная интерполяция между порогами
            synthetic_prob = 1.0 - ((variance - SYNTHETIC_VAR_THRESHOLD) / (NATURAL_VAR_THRESHOLD - SYNTHETIC_VAR_THRESHOLD))
            
        return round(synthetic_prob, 3)
        
    except Exception as e:
        print(f"Ошибка анализа текстуры {face_crop_path}: {e}")
        return 0.5
