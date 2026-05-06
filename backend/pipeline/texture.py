from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any

from skimage.feature import local_binary_pattern, graycomatrix, graycoprops
from skimage.filters import gabor, laplace
from skimage.measure import shannon_entropy
from skimage.feature import canny
from skimage import color as skcolor

_YAW_FRONTAL     = 20.0  # лоб, поры носа
_YAW_EYE_CORNERS = 20.0  # гусиные лапки, носогубные складки
_YAW_HALF        = 45.0  # щёки

@dataclass
class TextureMetrics:
    # UNIVERSAL group
    lbp_uniformity: Optional[float] = None
    lbp_entropy: Optional[float] = None
    glcm_contrast: Optional[float] = None
    glcm_energy: Optional[float] = None
    glcm_homogeneity: Optional[float] = None
    glcm_correlation: Optional[float] = None
    gabor_mean: Optional[float] = None
    gabor_std: Optional[float] = None
    laplacian_energy: Optional[float] = None
    spot_density: Optional[float] = None
    specular_gloss: Optional[float] = None
    skin_tone_std: Optional[float] = None
    pigmentation_index: Optional[float] = None

    # CONDITIONAL group
    wrinkle_forehead: Optional[float] = None
    nasolabial_depth: Optional[float] = None
    crow_feet_score: Optional[float] = None
    nose_pore_density: Optional[float] = None

    # UV ZONE group
    uv_spot_density: Optional[float] = None
    uv_wrinkle_energy: Optional[float] = None
    uv_texture_entropy: Optional[float] = None
    uv_silicone_flatness: Optional[float] = None
    uv_retouch_score: Optional[float] = None

    # QUALITY group
    quality_sharpness_score: Optional[float] = None
    quality_noise_score: Optional[float] = None
    quality_index: Optional[float] = None

    def as_dict(self) -> dict:
        return asdict(self)

def _load_gray_masked(img_path: Path, mask_path: Optional[Path] = None):
    """Load image in grayscale + RGB, apply mask if passed. Returns (gray, rgb, mask)."""
    img_rgba = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    if img_rgba is None:
        return None, None, None
    
    skin_mask = None
    if img_rgba.ndim == 3 and img_rgba.shape[2] == 4:
        alpha = img_rgba[:, :, 3]
        skin_mask = (alpha > 30).astype(np.uint8)
        bgr = img_rgba[:, :, :3]
    else:
        if img_rgba.ndim == 3:
            bgr = img_rgba
        else:
            bgr = cv2.cvtColor(img_rgba, cv2.COLOR_GRAY2BGR)
            
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    
    if mask_path and Path(mask_path).exists():
        raw_mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if raw_mask is not None:
            if raw_mask.shape != gray.shape:
                raw_mask = cv2.resize(raw_mask, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)
            skin_mask = (raw_mask > 0).astype(np.uint8)
            
    if skin_mask is None:
        skin_mask = (gray > 0).astype(np.uint8)
        
    return gray, rgb, skin_mask

def _apply_mask(arr: np.ndarray, mask: Optional[np.ndarray]) -> np.ndarray:
    if mask is not None and mask.size == arr.size:
        return arr[mask > 0].flatten()
    return arr.flatten()

def _roi_by_fraction(gray: np.ndarray, y0f: float, y1f: float, x0f: float, x1f: float) -> np.ndarray:
    h, w = gray.shape[:2]
    y0, y1 = int(y0f * h), int(y1f * h)
    x0, x1 = int(x0f * w), int(x1f * w)
    return gray[y0:y1, x0:x1]

class SkinTextureAnalyzer:
    def __init__(self):
        pass

    def analyze(
        self,
        face_crop_path: Path,
        uv_path: Optional[Path] = None,
        uv_mask_path: Optional[Path] = None,
        yaw_deg: float = 0.0,
        pitch_deg: float = 0.0,
    ) -> TextureMetrics:
        metrics = TextureMetrics()
        
        gray, rgb, skin_mask = _load_gray_masked(face_crop_path)
        if gray is None:
            return metrics

        masked_pixels = _apply_mask(gray, skin_mask)
        if masked_pixels.size == 0:
            return metrics

        # 1. UNIVERSAL Group
        # LBP Uniformity & Entropy
        lbp = local_binary_pattern(gray, P=8, R=1, method="uniform")
        lbp_masked = _apply_mask(lbp, skin_mask)
        if lbp_masked.size > 0:
            hist, _ = np.histogram(lbp_masked, bins=10, range=(0, 10), density=True)
            metrics.lbp_uniformity = float(np.sum(hist**2))
            metrics.lbp_entropy = float(-np.sum(hist * np.log(hist + 1e-9)))

        # GLCM
        gray_32 = (gray // 8).astype(np.uint8)
        glcm = graycomatrix(gray_32, distances=[1], angles=[0, np.pi/4], levels=32, symmetric=True, normed=True)
        metrics.glcm_contrast = float(np.mean(graycoprops(glcm, 'contrast')))
        metrics.glcm_energy = float(np.mean(graycoprops(glcm, 'energy')))
        metrics.glcm_homogeneity = float(np.mean(graycoprops(glcm, 'homogeneity')))
        metrics.glcm_correlation = float(np.mean(graycoprops(glcm, 'correlation')))

        # Gabor responses
        gabor_responses = []
        for freq in [0.1, 0.2, 0.3]:
            filt_real, filt_imag = gabor(gray, frequency=freq)
            gabor_responses.append(np.sqrt(filt_real**2 + filt_imag**2))
        gabor_stack = np.mean(gabor_responses, axis=0)
        # Нормализуем в [0,255] для корректной работы _apply_mask с uint8 маской
        gabor_norm = ((gabor_stack - gabor_stack.min()) /
                      ((np.max(gabor_stack) - np.min(gabor_stack)) + 1e-8) * 255).astype(np.float32)
        gabor_masked = _apply_mask(gabor_norm, skin_mask)
        if gabor_masked.size > 0:
            metrics.gabor_mean = float(np.mean(gabor_masked))
            metrics.gabor_std = float(np.std(gabor_masked))

        # Laplacian energy
        lap = laplace(gray)
        lap_masked = _apply_mask(lap, skin_mask)
        if lap_masked.size > 0:
            metrics.laplacian_energy = float(np.mean(lap_masked**2))

        # Spot density
        mean_val = np.mean(masked_pixels)
        std_val = np.std(masked_pixels)
        metrics.spot_density = float(np.sum(masked_pixels < (mean_val - 1.5 * std_val)) / masked_pixels.size)

        # Specular gloss
        p97 = np.percentile(masked_pixels, 97)
        bright_threshold = min(float(p97), 230.0)  # не ниже 230 чтобы отсечь нормальную кожу
        metrics.specular_gloss = float(np.sum(masked_pixels > bright_threshold) / masked_pixels.size)

        # Lab color features
        lab = skcolor.rgb2lab(rgb)
        l_chan = lab[:, :, 0]
        a_chan = lab[:, :, 1]
        l_masked = _apply_mask(l_chan, skin_mask)
        a_masked = _apply_mask(a_chan, skin_mask)
        if l_masked.size > 0:
            metrics.skin_tone_std = float(np.std(l_masked))
        if a_masked.size > 0:
            metrics.pigmentation_index = float(np.std(a_masked))

        # 2. CONDITIONAL Group
        # Forehead wrinkles
        if abs(yaw_deg) < _YAW_FRONTAL:
            roi_forehead = _roi_by_fraction(gray, 0.0, 0.30, 0.15, 0.85)
            if roi_forehead.size > 0:
                metrics.wrinkle_forehead = float(np.var(laplace(roi_forehead)))

        # Nasolabial depth
        if abs(yaw_deg) < _YAW_EYE_CORNERS:
            roi_nasolabial = _roi_by_fraction(gray, 0.50, 0.85, 0.20, 0.80)
            if roi_nasolabial.size > 0:
                metrics.nasolabial_depth = float(np.mean(canny(roi_nasolabial).astype(np.float32)))

        # Crow feet score
        if abs(yaw_deg) < _YAW_EYE_CORNERS:
            roi_eye_l = _roi_by_fraction(gray, 0.15, 0.45, 0.0, 0.20)
            roi_eye_r = _roi_by_fraction(gray, 0.15, 0.45, 0.80, 1.0)
            v_l = np.var(laplace(roi_eye_l)) if roi_eye_l.size > 0 else 0.0
            v_r = np.var(laplace(roi_eye_r)) if roi_eye_r.size > 0 else 0.0
            metrics.crow_feet_score = float((v_l + v_r) / 2.0)

        # Nose pore density
        if abs(yaw_deg) < _YAW_FRONTAL:
            roi_nose = _roi_by_fraction(gray, 0.35, 0.65, 0.30, 0.70)
            if roi_nose.size > 0:
                # Variance of Laplacian = мера резкости мелких деталей (поры, текстура)
                # Не зависит от абсолютной яркости и не требует порогов
                metrics.nose_pore_density = float(np.var(laplace(roi_nose.astype(np.float32))))

        # 3. UV ZONE Group
        if uv_path and Path(uv_path).exists():
            uv_gray = cv2.imread(str(uv_path), cv2.IMREAD_GRAYSCALE)
            if uv_gray is not None:
                uv_mask = None
                if uv_mask_path and Path(uv_mask_path).exists():
                    uv_mask = cv2.imread(str(uv_mask_path), cv2.IMREAD_GRAYSCALE)
                    if uv_mask is not None and uv_mask.shape != uv_gray.shape:
                        uv_mask = cv2.resize(uv_mask, (uv_gray.shape[1], uv_gray.shape[0]), interpolation=cv2.INTER_NEAREST)
                if uv_mask is None:
                    uv_mask = (uv_gray > 0).astype(np.uint8) * 255
                
                uv_pixels = _apply_mask(uv_gray, uv_mask)
                if uv_pixels.size > 0:
                    mean_uv = np.mean(uv_pixels)
                    std_uv = np.std(uv_pixels)
                    metrics.uv_spot_density = float(np.sum(uv_pixels < (mean_uv - 1.5 * std_uv)) / uv_pixels.size)
                    
                    import cv2 as _cv2
                    uv_gray_smooth = _cv2.GaussianBlur(uv_gray, (3, 3), sigmaX=0.8)
                    uv_lap = laplace(uv_gray_smooth.astype(np.float32))
                    uv_lap_masked = _apply_mask(uv_lap, uv_mask)
                    metrics.uv_wrinkle_energy = float(np.mean(uv_lap_masked**2))
                    
                    hist_uv, _ = np.histogram(uv_pixels, bins=64, range=(0, 256), density=True)
                    metrics.uv_texture_entropy = float(-np.sum(hist_uv * np.log(hist_uv + 1e-9)))
                    
                    uv_gray_32 = (uv_gray // 8).astype(np.uint8)
                    glcm_uv = graycomatrix(uv_gray_32, distances=[1], angles=[0], levels=32, symmetric=True, normed=True)
                    glcm_contrast_uv = float(np.mean(graycoprops(glcm_uv, 'contrast')))
                    metrics.uv_silicone_flatness = float(1.0 / (1.0 + glcm_contrast_uv))
                    
                    lbp_uv = local_binary_pattern(uv_gray, P=8, R=1, method="uniform")
                    lbp_uv_masked = _apply_mask(lbp_uv, uv_mask)
                    if lbp_uv_masked.size > 0:
                        hist_lbp_uv, _ = np.histogram(lbp_uv_masked, bins=10, range=(0, 10), density=True)
                        metrics.uv_retouch_score = float(np.sum(hist_lbp_uv**2))

        # 4. QUALITY Group
        metrics.quality_sharpness_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        metrics.quality_noise_score = float(np.std(masked_pixels))
        q_index_sharp = metrics.quality_sharpness_score / (metrics.quality_sharpness_score + 500.0 + 1e-9)
        q_index_gloss = 1.0 - (metrics.specular_gloss or 0.0) * 10.0
        metrics.quality_index = float(np.clip(q_index_sharp * q_index_gloss, 0.0, 1.0))

        return metrics

    def analyze_image(
        self,
        face_crop_path: Path,
        uv_path: Optional[Path] = None,
        uv_mask_path: Optional[Path] = None,
        yaw_deg: float = 0.0,
        pitch_deg: float = 0.0,
    ) -> Dict[str, Any]:
        metrics = self.analyze(
            face_crop_path=face_crop_path,
            uv_path=uv_path,
            uv_mask_path=uv_mask_path,
            yaw_deg=yaw_deg,
            pitch_deg=pitch_deg,
        )
        return metrics.as_dict()

def analyze_texture_synthetic_prob(face_crop_path: str) -> float:
    try:
        img = cv2.imread(face_crop_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return 0.5
        laplacian = cv2.Laplacian(img, cv2.CV_64F)
        variance = laplacian.var()
        NATURAL_VAR_THRESHOLD = 500.0
        SYNTHETIC_VAR_THRESHOLD = 100.0
        if variance > NATURAL_VAR_THRESHOLD:
            synthetic_prob = 0.05
        elif variance < SYNTHETIC_VAR_THRESHOLD:
            synthetic_prob = 0.95
        else:
            synthetic_prob = 1.0 - ((variance - SYNTHETIC_VAR_THRESHOLD) / (NATURAL_VAR_THRESHOLD - SYNTHETIC_VAR_THRESHOLD))
        return round(synthetic_prob, 3)
    except Exception as e:
        print(f"Ошибка анализа текстуры {face_crop_path}: {e}")
        return 0.5
