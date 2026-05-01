from __future__ import annotations

import math
import threading
from pathlib import Path
import sys
from typing import Any, Dict
from pydantic import BaseModel

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from pipeline.detect_pose import PoseDetector
from pipeline.quality_gate import QualityGate
from pipeline.reconstruction import ReconstructionAdapter, ReconstructionResult, resolve_reconstruction
from pipeline.scoring import extract_macro_bone_metrics
from pipeline.texture import SkinTextureAnalyzer
from pipeline.zones import MACRO_BONE_INDICES
from backend.core.calibration import (
    get_epoch_noise_model,
    compute_calibration_informed_likelihood,
    find_calibration_match,
)
from backend.core.longitudinal import (
    LongitudinalAnalyzer,
    build_longitudinal_model,
)
try:
    from uv_module.hd_uv_generator import HDUVConfig, HDUVTextureGenerator
    _UV_AVAILABLE = True
except ImportError:
    _UV_AVAILABLE = False
    HDUVConfig = None  # type: ignore
    HDUVTextureGenerator = None  # type: ignore

from .config import SETTINGS
from .constants import (
    ALIGNMENT_MIN_RANK,
    ARTIFACT_VERSION,
    MIN_ZONE_VERTICES,
)
from .utils import (
    BUCKET_METRIC_KEYS,
    RAW_BUCKET_TO_UI,
    ForensicManifest,
    ensure_directory,
    iso_now,
    read_json,
    runtime_config_snapshot,
    write_json,
)

_RUNTIME_LOCK = threading.Lock()
_RUNTIME: "LegacyRuntime | None" = None


class BayesianEvidence(BaseModel):
    h0_same_person: float
    h1_synthetic_mask: float
    h2_different_person: float
    structural_snr: float
    anomalies_flagged: int


# Веса зон по реальным ключам из BUCKET_METRIC_KEYS.
# Приоритет на неизменные костные структуры согласно ТЗ.
# [FIX-1] Расширено до полного набора 21 зоны с анатомически обоснованными весами.
ZONE_WEIGHTS = {
    # === Костные структуры (максимальный приоритет, вес 1.0) ===
    # Эти зоны формируются в раннем возрасте и не меняются на протяжении жизни
    "nose_projection_ratio": 1.0,   # Проекция носа (переносица) — костная основа
    "orbit_depth_L_ratio": 1.0,     # Глубина левой глазницы — костная структура
    "orbit_depth_R_ratio": 1.0,     # Глубина правой глазницы — костная структура
    "jaw_width_ratio": 0.95,        # Ширина челюсти — костная структура
    "cranial_face_index": 0.95,     # Краниальный индекс — соотношение черепа и лица

    # === Костно-связочные зоны (высокий приоритет, вес 0.8-0.9) ===
    "chin_projection_ratio": 0.9,   # Проекция подбородка
    "gonial_angle_L": 0.85,         # Угол нижней челюсти L — гониальный угол
    "gonial_angle_R": 0.85,         # Угол нижней челюсти R
    "canthal_tilt_L": 0.8,          # Кантальный угол L — связочная структура
    "canthal_tilt_R": 0.8,          # Кантальный угол R
    "nasofacial_angle_ratio": 0.8,  # Угол носа к лицу

    # === Зоны симметрии и асимметрии (средний приоритет, вес 0.7) ===
    # Используются для выявления структурных несоответствий
    "chin_offset_asymmetry": 0.7,   # Асимметрия подбородка
    "nasal_frontal_index": 0.7,     # Индекс переносицы
    "forehead_slope_index": 0.7,    # Угол наклона лба

    # === Мягкие ткани и текстура (низкий приоритет, вес 0.2-0.4) ===
    # Подвержены временным изменениям, но полезны для детекции синтетики
    "texture_silicone_prob": 0.3,   # Вероятность силикона (мягкие ткани)
    "texture_pore_density": 0.25,     # Плотность пор — биологический маркер
    "nose_width_ratio": 0.25,       # Ширина носа (включает мягкие ткани крыльев)
    "texture_wrinkle_forehead": 0.2, # Морщины лба — возрастной маркер
    "texture_wrinkle_nasolabial": 0.2, # Носогубные складки
    "texture_spot_density": 0.2,    # Плотность пигментных пятен
    "texture_global_smoothness": 0.15, # Общая гладкость (инверсия пор)
    "interorbital_ratio": 0.15,     # Межглазничное расстояние (менее стабильно)
}


# [FIX-2] Зоны, чувствительные к разным выражениям лица согласно ТЗ
EXPRESSION_EXCLUDED_ZONES = {
    "smile": ["texture_wrinkle_nasolabial", "nose_width_ratio", "texture_global_smoothness"],  # Щёки, носогубные
    "open_mouth": ["chin_projection_ratio", "jaw_width_ratio"],  # Челюсть
    "squint": ["canthal_tilt_L", "canthal_tilt_R", "orbit_depth_L_ratio", "orbit_depth_R_ratio"],  # Глаза
    "eyebrow_raise": ["forehead_slope_index", "texture_wrinkle_forehead"],  # Лоб, брови
    "tense_jaw": ["gonial_angle_L", "gonial_angle_R", "jaw_width_ratio"],  # Напряжение челюсти
}

# Категории зон для структурированного анализа
ZONE_CATEGORIES = {
    "bone": ["nose_projection_ratio", "orbit_depth_L_ratio", "orbit_depth_R_ratio",
             "jaw_width_ratio", "cranial_face_index", "chin_projection_ratio"],
    "ligament": ["canthal_tilt_L", "canthal_tilt_R", "gonial_angle_L", "gonial_angle_R",
                 "nasofacial_angle_ratio"],
    "symmetry": ["chin_offset_asymmetry"],
    "nasal": ["nose_width_ratio", "nasal_frontal_index", "nasofacial_angle_ratio"],
    "soft_tissue": ["texture_silicone_prob", "texture_pore_density", "texture_spot_density",
                    "texture_wrinkle_forehead", "texture_wrinkle_nasolabial", "texture_global_smoothness"],
    "cranial": ["cranial_face_index", "forehead_slope_index", "interorbital_ratio"],
}


def _detect_excluded_zones(pose_a: Dict[str, Any], pose_b: Dict[str, Any]) -> set:
    """
    [FIX-3] Динамическое исключение зон на основе выражений обоих фото.
    Возвращает множество зон, которые должны быть исключены из анализа.
    """
    excluded = set()
    expr_a = pose_a.get("expression", "neutral")
    expr_b = pose_b.get("expression", "neutral")
    
    for expr in [expr_a, expr_b]:
        if expr in EXPRESSION_EXCLUDED_ZONES:
            excluded.update(EXPRESSION_EXCLUDED_ZONES[expr])
    
    # Дополнительная эвристика: если амплитуда морщин высокая — считаем выражением
    # (в реальной системе здесь был бы детектор AU из MediaPipe или аналог)
    
    return excluded


def _get_missing_metrics(metrics: Dict[str, Any], required_zones: list) -> list:
    """Возвращает список зон, для которых отсутствуют метрики."""
    return [zone for zone in required_zones if zone not in metrics or metrics[zone] is None]


def _calculate_real_snr(
    zone_deltas: Dict[str, float],
    zone_weights: Dict[str, float],
    calibration_stats: Dict[str, Any] | None = None
) -> float:
    """
    [FIX-6] Расчёт реального SNR на основе зональных отклонений.
    Если есть калибровка — используем sigma из калибровки.
    Иначе — эвристику на основе ZONE_WEIGHTS.
    """
    if not zone_deltas:
        return 0.0
    
    # Взвешенное среднее отклонений
    weighted_delta_sum = sum(
        delta * zone_weights.get(zone, 0.5)
        for zone, delta in zone_deltas.items()
    )
    total_weight = sum(zone_weights.get(zone, 0.5) for zone in zone_deltas.keys())
    
    if total_weight == 0:
        return 0.0
    
    mean_weighted_delta = weighted_delta_sum / total_weight
    
    # SNR = сигнал / шум. Для H0 (same person) ожидаем delta ≈ 0
    # Чем больше delta — тем ниже SNR
    if calibration_stats and "sigma_noise" in calibration_stats:
        sigma = calibration_stats["sigma_noise"]
        if sigma > 0:
            snr = 10.0 * math.log10((sigma ** 2) / (mean_weighted_delta ** 2 + 1e-9))
            return max(-20.0, min(30.0, snr))
    
    # Fallback: эвристический SNR на основе дивергенции
    # Нормализуем к диапазону [0, 10] для UI
    snr_linear = max(0.0, 1.0 - mean_weighted_delta * 5.0)
    snr_db = 10.0 * math.log10(snr_linear + 1e-9) if snr_linear > 0 else -20.0
    return max(0.0, snr_db + 20.0)  # Сдвигаем к положительному диапазону для UI


def _compute_adaptive_priors(
    summary_a: Dict[str, Any],
    summary_b: Dict[str, Any],
    base_priors: Dict[str, float] | None = None
) -> Dict[str, float]:
    """
    [FIX-7] Адаптивные априоры на основе метаданных пар.
    Учитываем: временной интервал, качество, ракурс.
    """
    if base_priors is None:
        base_priors = {"H0": 0.78, "H1": 0.02, "H2": 0.20}
    
    priors = dict(base_priors)
    
    # Адаптация по временному интервалу
    year_a = summary_a.get("year", summary_a.get("parsed_year", 2000))
    year_b = summary_b.get("year", summary_b.get("parsed_year", 2000))
    delta_years = abs(year_a - year_b)
    
    if delta_years > 20:
        # Долгий интервал — повышаем вероятность H2 (different)
        priors["H2"] = min(0.40, priors["H2"] + 0.15)
        priors["H0"] = max(0.60, priors["H0"] - 0.10)
    elif delta_years < 2:
        # Короткий интервал — повышаем H0
        priors["H0"] = min(0.90, priors["H0"] + 0.05)
        priors["H2"] = max(0.10, priors["H2"] - 0.05)
    
    # Нормализуем
    total = sum(priors.values())
    return {k: v / total for k, v in priors.items()}


def _get_epoch_texture_adjustments(year: int) -> Dict[str, float]:
    """
    [FIX-10] Эпохальная калибровка текстурных признаков.
    Старые фото (1999-2005) имеют деградацию от сканирования/времени.
    Новые фото (2015-2025) имеют высокое разрешение, но риск ретуши.
    """
    if year < 2005:
        # Аналоговая эпоха: шум сканирования, деградация
        return {
            "fft_boost": 0.15,      # Компенсация потери высоких частот
            "albedo_tolerance": 0.20,  # Больше толерантности к неравномерности
            "specular_discount": 0.30,  # Старые фото менее глянцевые
            "lbp_bias": -0.10,      # Коррекция на шум
            "silicone_threshold_boost": 0.10,  # Повышаем порог для старых
        }
    elif year < 2015:
        # Переходная эпоха (2005-2015): цифровые фото начального уровня
        return {
            "fft_boost": 0.05,
            "albedo_tolerance": 0.10,
            "specular_discount": 0.10,
            "lbp_bias": -0.05,
            "silicone_threshold_boost": 0.05,
        }
    else:
        # Современная эпоха (2015-2025): высокое разрешение, но ретушь
        return {
            "fft_boost": 0.0,
            "albedo_tolerance": 0.0,
            "specular_discount": 0.0,
            "lbp_bias": 0.0,
            "silicone_threshold_boost": 0.0,  # Нормальный порог
        }


def _determine_bucket_from_pose(pose: Dict[str, Any]) -> str:
    """
    Определяет pose bucket из yaw/pitch/roll.
    Упрощенная версия PoseDetector.get_bucket_name.
    """
    yaw = abs(float(pose.get("yaw", 0.0)))
    
    # Типичные диапазоны bucket-ов
    if yaw <= 10:
        return "frontal"
    elif yaw <= 25:
        return "right_threequarter" if pose.get("yaw", 0) > 0 else "left_threequarter"
    elif yaw <= 50:
        return "right_profile" if pose.get("yaw", 0) > 0 else "left_profile"
    else:
        return "unclassified"


def _classify_h1_subtype(
    texture_features: Dict[str, float],
    geometric_divergence: float,
    tex_a: Dict[str, Any],
    tex_b: Dict[str, Any],
) -> Dict[str, Any]:
    """
    [FIX-19] Классификация подтипа синтетики (H1) на основе текстурных и геометрических признаков.
    
    Подтипы:
    - mask: физическая маска (высокий specular, низкая геометрическая аномальность)
    - deepfake: цифровая подмена (высокий FFT anomaly, средняя геометрия)
    - prosthetic: протез/имплант (высокий silicone, локальная геометрическая аномалия)
    - uncertain: неопределенно
    
    Returns:
        {
            "primary": str,  # Основной подтип
            "confidence": float,  # Уверенность в классификации [0, 1]
            "scores": {
                "mask": float,
                "deepfake": float,
                "prosthetic": float,
            },
            "indicators": List[str],  # Ключевые индикаторы
        }
    """
    scores = {
        "mask": 0.0,
        "deepfake": 0.0,
        "prosthetic": 0.0,
        "uncertain": 0.0,
    }
    indicators = []
    
    # 1. Признаки физической маски
    # - Высокий specular gloss (пластик/силикон отражает иначе)
    # - Низкая/средняя геометрическая аномальность (маска повторяет форму лица)
    # - Высокая uniformity текстуры
    # [FIX-C4] Нет дефолта 0.5 — None для отсутствующих метрик
    specular = texture_features.get("specular_gloss")
    lbp_uniformity = texture_features.get("lbp_uniformity")
    
    if specular is not None and lbp_uniformity is not None:
        if specular > 0.6 and lbp_uniformity > 0.5 and geometric_divergence < 0.3:
            scores["mask"] = 0.7 + (specular - 0.6) * 0.5
            indicators.append("high_specular_uniformity")
        elif specular > 0.5:
            scores["mask"] = 0.4
    
    # 2. Признаки дипфейка
    # - Высокий FFT anomaly (артефакты генерации)
    # - Низкий pore density (сглаживание)
    # - Средняя геометрическая аномальность
    fft_anomaly = texture_features.get("fft_anomaly")  # [FIX-C4] No default 0.5
    pore_density = (float(tex_a.get("pore_density", 25)) + float(tex_b.get("pore_density", 25))) / 2
    
    if fft_anomaly is not None:
        if fft_anomaly > 0.55 and pore_density < 30 and 0.15 < geometric_divergence < 0.5:
            scores["deepfake"] = 0.6 + (fft_anomaly - 0.55) * 0.8
            indicators.append("fft_artifacts_low_pores")
        elif fft_anomaly > 0.5:
            scores["deepfake"] = 0.35
    
    # 3. Признаки протеза/импланта
    # - Высокий silicone_probability (локальная область)
    # - Высокая геометрическая аномальность (несоответствие структуры)
    # - Нормальная текстура вне области импланта
    silicone = texture_features.get("silicone", 0.0)
    
    if silicone > 0.5 and geometric_divergence > 0.3:
        scores["prosthetic"] = 0.65 + (silicone - 0.5) * 0.5
        indicators.append("silicone_with_geometry_mismatch")
    elif silicone > 0.4:
        scores["prosthetic"] = 0.4
    
    # Нормализация scores
    total = sum(scores.values())
    if total > 0:
        scores = {k: v / total for k, v in scores.items()}
    else:
        scores["uncertain"] = 1.0
        indicators.append("insufficient_indicators")
    
    # Определение primary подтипа
    primary = max(scores, key=scores.get)
    confidence = scores[primary]
    
    return {
        "primary": primary,
        "confidence": round(confidence, 3),
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "indicators": indicators,
    }


def _compute_texture_h1_evidence(
    tex_a: Dict[str, Any],
    tex_b: Dict[str, Any],
    year_a: int = 2000,
    year_b: int = 2000,
) -> Dict[str, float]:
    """
    [FIX-8, FIX-10, FIX-16, FIX-17, FIX-19] Расширенная модель H1 с эпохальной калибровкой,
    симметричным отрицательным доказательством H0 и классификацией подтипов.
    
    Исправления:
    - Не max(), а взвешенное среднее признаков (FIX-16)
    - Добавлено отрицательное доказательство (естественность) для H0 (FIX-17)
    - Корректировка для старых фото (1999-2005) vs новых (2015-2025)
    - Классификация подтипа синтетики: mask, deepfake, prosthetic (FIX-19)
    """
    # Эпохальные корректировки
    adj_a = _get_epoch_texture_adjustments(year_a)
    adj_b = _get_epoch_texture_adjustments(year_b)
    # Берём средние корректировки (не максимум, чтобы не преувеличивать)
    epoch_adj = {
        k: (adj_a.get(k, 0) + adj_b.get(k, 0)) / 2
        for k in set(adj_a.keys()) | set(adj_b.keys())
    }
    
    # [FIX-16] Вместо max() используем взвешенное среднее признаков
    # [FIX-C4] Нет дефолта 0.5 — None для отсутствующих метрик
    raw_silicone_a = tex_a.get("silicone_probability")
    raw_silicone_b = tex_b.get("silicone_probability")
    raw_fft_a = tex_a.get("fft_high_freq_ratio")
    raw_fft_b = tex_b.get("fft_high_freq_ratio")
    raw_albedo_a = tex_a.get("albedo_uniformity")
    raw_albedo_b = tex_b.get("albedo_uniformity")
    raw_spec_a = tex_a.get("specular_gloss")
    raw_spec_b = tex_b.get("specular_gloss")
    raw_lbp_a = tex_a.get("lbp_uniformity")
    raw_lbp_b = tex_b.get("lbp_uniformity")
    
    # Взвешенное среднее (не максимум)
    # [FIX-C4] Пропускаем None значения в среднем — не используем 0.5 как дефолт
    def safe_avg(a, b):
        if a is None and b is None:
            return None
        if a is None:
            return float(b)
        if b is None:
            return float(a)
        return (float(a) + float(b)) / 2
    
    silicone_combined = safe_avg(raw_silicone_a, raw_silicone_b)
    fft_combined = safe_avg(raw_fft_a, raw_fft_b)
    if fft_combined is not None:
        fft_combined += epoch_adj.get("fft_boost", 0)
    albedo_combined = safe_avg(raw_albedo_a, raw_albedo_b)
    if albedo_combined is not None:
        albedo_combined = 1.0 - albedo_combined + epoch_adj.get("albedo_tolerance", 0)
    specular_combined = safe_avg(raw_spec_a, raw_spec_b)
    if specular_combined is not None:
        specular_combined -= epoch_adj.get("specular_discount", 0)
    lbp_combined = safe_avg(raw_lbp_a, raw_lbp_b)
    if lbp_combined is not None:
        lbp_combined += epoch_adj.get("lbp_bias", 0)
    
    # [FIX-17] Отрицательное доказательство для H0 (естественность текстуры)
    # Чем больше признаков естественной кожи - тем ниже вероятность синтетики
    natural_markers = {
        "pore_density": (float(tex_a.get("pore_density", 0.0)) + float(tex_b.get("pore_density", 0.0))) / 2,
        "lbp_complexity": (float(tex_a.get("lbp_complexity", 0.0)) + float(tex_b.get("lbp_complexity", 0.0))) / 2,
        "wrinkle_detail": (
            float(tex_a.get("wrinkle_forehead", 0.0)) + float(tex_a.get("wrinkle_nasolabial", 0.0)) +
            float(tex_b.get("wrinkle_forehead", 0.0)) + float(tex_b.get("wrinkle_nasolabial", 0.0))
        ) / 4,
    }
    
    # Нормализованный score естественности [0, 1]
    # Высокие значения pore_density, lbp_complexity, wrinkle_detail = естественная кожа
    natural_score = (
        min(1.0, natural_markers["pore_density"] / 50.0) * 0.4 +
        min(1.0, natural_markers["lbp_complexity"] / 3.0) * 0.35 +
        min(1.0, natural_markers["wrinkle_detail"] / 20.0) * 0.25
    )
    
    # [FIX-C4] Фильтруем None значения — не используем 0.5 как дефолт
    features = {
        "silicone": silicone_combined,
        "fft_anomaly": fft_combined,
        "albedo_uniformity": albedo_combined,
        "specular_gloss": specular_combined,
        "lbp_uniformity": lbp_combined,
    }
    # Убираем None значения из расчёта
    valid_features = {k: v for k, v in features.items() if v is not None}
    
    # Ансамбль: взвешенное среднее с приоритет silicone
    weights = {"silicone": 0.35, "fft_anomaly": 0.20, "albedo_uniformity": 0.15,
               "specular_gloss": 0.15, "lbp_uniformity": 0.15}
    
    # [FIX-17] Adjust composite score by natural evidence
    # [FIX-C4] Нормализуем веса для доступных признаков
    if not valid_features:
        # Нет данных — нейтральный likelihood
        return {"likelihood": 0.5, "composite_score": 0.5, "raw_composite": 0.5,
                "features": features, "natural_score": natural_score,
                "note": "insufficient_texture_data"}
    
    available_weight = sum(weights[k] for k in valid_features)
    normalized_weights = {k: weights[k] / available_weight for k in valid_features}
    
    raw_composite = sum(valid_features[k] * normalized_weights[k] for k in valid_features)
    composite_score = raw_composite * (1.0 - natural_score * 0.5)  # Естественность снижает синтетику
    
    # Sigmoid с адаптивным порогом
    # [FIX-C4] Пропускаем None значения при подсчёте
    base_threshold = 0.35 + 0.05 * (sum(1 for v in valid_features.values() if v > 0.5) - 1)
    threshold = base_threshold + epoch_adj.get("silicone_threshold_boost", 0)
    l_h1_tex = 1.0 / (1.0 + math.exp(-10.0 * (composite_score - threshold)))
    
    # [FIX-19] Классификация подтипа H1 (откладывается до момента вызова, т.к. нужен geometric_divergence)
    # Возвращаем features для использования в classify позже
    return {
        "likelihood": l_h1_tex,
        "composite_score": composite_score,
        "raw_composite": raw_composite,
        "features": features,
        "naturalScore": natural_score,
        "naturalMarkers": natural_markers,
        "epochAdjustments": epoch_adj,
        "threshold": threshold,
        # subtype будет добавлен в calculate_bayesian_evidence где есть geometric_divergence
    }


# Версия методологии для traceability и reproducibility
METHODOLOGY_VERSION = "ITER-6.5-2025-05-01"


def calculate_bayesian_evidence(
    summary_a: Dict[str, Any],
    summary_b: Dict[str, Any],
    calibration_stats: Dict[str, Any] | None = None,
    longitudinal_model: LongitudinalAnalyzer | None = None,
) -> Dict[str, Any]:
    """
    [ITER-6.5] Forensic Bayesian Evidence Breakdown — исправленная версия с traceability.
    
    Исправленные ошибки:
    - [FIX-1] Полный набор 21 зоны в ZONE_WEIGHTS
    - [FIX-2] Динамическое исключение зон по мимике (smile, open_mouth, squint, eyebrow_raise)
    - [FIX-3] Нет подстановки 0.5 — NULL для отсутствующих метрик с отслеживанием покрытия
    - [FIX-4] Зональный анализ вместо mean_divergence
    - [FIX-5] Реальный SNR через _calculate_real_snr
    - [FIX-6] Адаптивные априоры через _compute_adaptive_priors
    - [FIX-7] H1 на ансамбле текстурных признаков, не только silicone
    - [FIX-8] Quality и reliability интегрированы в веса
    - [FIX-9] Methodology version и computation log для traceability
    - [FIX-10] Эпохальная калибровка текстурных признаков (1999-2005 vs 2015-2025)
    - [FIX-12] Плавная маска вместо бинарной (> 0.5) для сегментации кожи
    - [FIX-13] PNG вместо JPEG (без потерь) для forensic-качества
    - [FIX-14] Альфа-канал для взвешенной маски в текстурном анализе
    - [FIX-15] Детекция и корректировка студийного света и ретуши
    - [FIX-16] Взвешенное среднее вместо max() для текстурных признаков
    - [FIX-17] Симметричное отрицательное доказательство H0 (естественность текстуры)
    - [FIX-19] Классификация подтипа H1: mask, deepfake, prosthetic
    - [FIX-11] Интеграция калибровки в формулу правдоподобия
    - [FIX-15] Поиск калибровочной пары по углам и эпохе
    - [FIX-34] Noise model для разных эпох фото
    - [FIX-77, FIX-78] Защита от сравнения неполных/pending данных
    - [FIX-28, FIX-30] Longitudinal анализ вместо только pairwise
    - [FIX-31, FIX-36] Хронология как полноценное доказательство в байесовской схеме
    """
    # [FIX-77, FIX-78] Проверяем статусы перед сравнением
    status_a = summary_a.get("status", "unknown")
    status_b = summary_b.get("status", "unknown")
    status_detail_a = summary_a.get("status_detail", {})
    status_detail_b = summary_b.get("status_detail", {})
    
    # Если данные не готовы — возвращаем ошибку
    if status_a != "ready" or status_b != "ready":
        return {
            "aId": summary_a.get("photo_id"),
            "bId": summary_b.get("photo_id"),
            "verdict": "INSUFFICIENT_DATA",
            "error": f"One or both photos not ready: A={status_a}, B={status_b}",
            "geometric": {
                "snr": 0,
                "boneScore": 0,
                "ligamentScore": 0,
                "softTissueScore": 0,
                "zoneCount": 0,
                "excludedZones": [],
                "categoryDivergence": {}
            },
            "texture": {
                "syntheticProb": 0,
                "fft": 0.5,
                "lbp": 0.5,
                "albedo": 0.5,
                "specular": 0.5,
                "textureFeatures": {}
            },
            "chronology": {
                "deltaYears": 0,
                "boneJump": 0,
                "ligamentJump": 0,
                "flags": []
            },
            "pose": {
                "mutualVisibility": 0,
                "expressionExcluded": 0,
                "poseDistanceDeg": 0
            },
            "dataQuality": {
                "coverageRatio": 0,
                "missingZonesA": [],
                "missingZonesB": []
            },
            "likelihoods": {
                "H0": 0.33,
                "H1": 0.33,
                "H2": 0.34
            },
            "priors": {"H0": 0.78, "H1": 0.02, "H2": 0.20},
            "posteriors": {"H0": 0.33, "H1": 0.33, "H2": 0.34},
            "methodologyVersion": METHODOLOGY_VERSION,
            "computationLog": [
                f"ERROR: Cannot compare — photo A status={status_a}, photo B status={status_b}",
                "Required: both status='ready' and usable_for_comparison=true",
            ],
        }
    
    # Проверяем пригодность для сравнения
    usable_a = status_detail_a.get("usable_for_comparison", True)
    usable_b = status_detail_b.get("usable_for_comparison", True)
    
    if not (usable_a and usable_b):
        return {
            "aId": summary_a.get("photo_id"),
            "bId": summary_b.get("photo_id"),
            "verdict": "INSUFFICIENT_DATA",
            "error": f"Photo quality insufficient for comparison: A={usable_a}, B={usable_b}",
            "geometric": {
                "snr": 0,
                "boneScore": 0,
                "ligamentScore": 0,
                "softTissueScore": 0,
                "zoneCount": 0,
                "excludedZones": [],
                "categoryDivergence": {}
            },
            "texture": {
                "syntheticProb": 0,
                "fft": 0.5,
                "lbp": 0.5,
                "albedo": 0.5,
                "specular": 0.5,
                "textureFeatures": {}
            },
            "chronology": {
                "deltaYears": 0,
                "boneJump": 0,
                "ligamentJump": 0,
                "flags": []
            },
            "pose": {
                "mutualVisibility": 0,
                "expressionExcluded": 0,
                "poseDistanceDeg": 0
            },
            "dataQuality": {
                "coverageRatio": 0,
                "missingZonesA": [],
                "missingZonesB": []
            },
            "likelihoods": {
                "H0": 0.33,
                "H1": 0.33,
                "H2": 0.34
            },
            "priors": {"H0": 0.78, "H1": 0.02, "H2": 0.20},
            "posteriors": {"H0": 0.33, "H1": 0.33, "H2": 0.34},
            "methodologyVersion": METHODOLOGY_VERSION,
            "computationLog": [
                f"ERROR: Photo quality insufficient — A usable={usable_a}, B usable={usable_b}",
                f"A: quality={status_detail_a.get('quality_status')}, pose={status_detail_a.get('pose_status')}",
                f"B: quality={status_detail_b.get('quality_status')}, pose={status_detail_b.get('pose_status')}",
            ],
        }
    
    # [FIX-82] Проверяем версии методологий — предупреждаем если различаются
    method_a = summary_a.get("methodology_version", "unknown")
    method_b = summary_b.get("methodology_version", "unknown")
    method_current = METHODOLOGY_VERSION
    
    metrics_a = summary_a.get("metrics", {})
    metrics_b = summary_b.get("metrics", {})
    tex_a = summary_a.get("texture_forensics", {})
    tex_b = summary_b.get("texture_forensics", {})
    pose_a = summary_a.get("pose", {})
    pose_b = summary_b.get("pose", {})
    quality_a = summary_a.get("quality", {})
    quality_b = summary_b.get("quality", {})
    
    # [FIX-2] Определяем исключённые зоны по выражениям
    excluded_zones = _detect_excluded_zones(pose_a, pose_b)
    
    # [FIX-3] Отслеживаем покрытие данных
    missing_a = _get_missing_metrics(metrics_a, list(ZONE_WEIGHTS.keys()))
    missing_b = _get_missing_metrics(metrics_b, list(ZONE_WEIGHTS.keys()))
    coverage_ratio = 1.0 - (len(set(missing_a + missing_b)) / (2 * len(ZONE_WEIGHTS)))
    
    # 1. Зональный геометрический анализ
    zone_deltas = {}
    category_scores = {cat: [] for cat in ZONE_CATEGORIES}
    
    for zone, weight in ZONE_WEIGHTS.items():
        # Пропускаем исключённые зоны
        if zone in excluded_zones:
            continue
        
        # [FIX-3] НЕ подставляем 0.5 — пропускаем отсутствующие
        if zone not in metrics_a or zone not in metrics_b:
            continue
        
        val_a = metrics_a[zone]
        val_b = metrics_b[zone]
        
        # Проверка на None/NULL
        if val_a is None or val_b is None:
            continue
        
        # [FIX-8] Quality weight: чем ниже quality — тем ниже вес зоны
        q_weight_a = quality_a.get("overall_score", 1.0) if isinstance(quality_a, dict) else 1.0
        q_weight_b = quality_b.get("overall_score", 1.0) if isinstance(quality_b, dict) else 1.0
        q_weight = min(q_weight_a, q_weight_b)
        
        # Reliability из метрик
        rel_a = metrics_a.get("reliability_weight", 1.0)
        rel_b = metrics_b.get("reliability_weight", 1.0)
        rel_weight = min(rel_a, rel_b)
        
        # Итоговый вес зоны
        effective_weight = weight * q_weight * rel_weight
        
        delta = abs(float(val_a) - float(val_b))
        zone_deltas[zone] = delta
        
        # Группировка по категориям
        for cat, zones in ZONE_CATEGORIES.items():
            if zone in zones:
                category_scores[cat].append((delta, effective_weight))
    
    # 2. Расчёт SNR и скоров по категориям
    structural_snr = _calculate_real_snr(zone_deltas, ZONE_WEIGHTS, calibration_stats)
    
    def _weighted_mean(items: list) -> float:
        if not items:
            return 0.0
        total_weight = sum(w for _, w in items)
        if total_weight == 0:
            return 0.0
        return sum(d * w for d, w in items) / total_weight
    
    category_divergence = {cat: _weighted_mean(items) for cat, items in category_scores.items()}
    
    # [FIX-54] Age-aware weighting: различаем допустимую динамику костных и мягких зон
    # Костные метрики стабильны на протяжении жизни (кроме челюсти до 25)
    # Мягкие ткани меняются с возрастом (морщины, плотность пор, объем)
    delta_years = abs(year_a - year_b) if 'year_a' in locals() else 10  # Значение по умолчанию
    
    # Коэффициенты взвешивания в зависимости от временного интервала
    if delta_years < 5:
        # Короткий интервал — все зоны равноправны
        bone_weight_factor = 1.0
        soft_weight_factor = 1.0
        ligament_weight_factor = 1.0
    elif delta_years < 15:
        # Средний интервал — мягкие ткани начинают меняться
        bone_weight_factor = 1.0  # Кость стабильна
        soft_weight_factor = 0.8  # Мягкие ткани меняются
        ligament_weight_factor = 0.9
    else:
        # Длинный интервал (1999→2025 = 26 лет) — сильно различаем
        bone_weight_factor = 1.2  # Кость ключевая для идентификации
        soft_weight_factor = 0.5  # Мягкие ткани сильно изменились
        ligament_weight_factor = 0.8
    
    # Bone score — среднее расхождение по костным зонам (с age-aware weighting)
    bone_deltas = [zone_deltas.get(z, 0.0) for z in ZONE_CATEGORIES["bone"] if z in zone_deltas]
    bone_delta_sum = (sum(bone_deltas) / max(len(bone_deltas), 1) if bone_deltas else 0.0) * bone_weight_factor
    
    # Ligament score
    lig_deltas = [zone_deltas.get(z, 0.0) for z in ZONE_CATEGORIES["ligament"] if z in zone_deltas]
    ligament_delta_sum = (sum(lig_deltas) / max(len(lig_deltas), 1) if lig_deltas else 0.0) * ligament_weight_factor
    
    # Soft tissue score
    soft_deltas = [zone_deltas.get(z, 0.0) for z in ZONE_CATEGORIES["soft_tissue"] if z in zone_deltas]
    soft_delta_sum = (sum(soft_deltas) / max(len(soft_deltas), 1) if soft_deltas else 0.0) * soft_weight_factor
    
    # Сохраняем weight factors для explainability
    age_weight_factors = {
        "bone": bone_weight_factor,
        "ligament": ligament_weight_factor,
        "soft_tissue": soft_weight_factor,
        "delta_years": delta_years,
    }
    
    # 3. Расширенная текстурная модель H1 с эпохальной калибровкой
    h1_texture = _compute_texture_h1_evidence(tex_a, tex_b, year_a, year_b)
    l_h1_tex = h1_texture["likelihood"]
    
    # [FIX-19] Классификация подтипа H1 (mask, deepfake, prosthetic)
    # Используем bone_delta_sum как показатель геометрической аномальности
    h1_subtype = _classify_h1_subtype(
        h1_texture["features"],
        bone_delta_sum,  # Геометрическая дивергенция
        tex_a,
        tex_b,
    )
    
    # [FIX-34] Получаем noise model для эпох обоих фото
    year_a = summary_a.get("year", summary_a.get("parsed_year", 2000))
    year_b = summary_b.get("year", summary_b.get("parsed_year", 2000))
    epoch_model_a = get_epoch_noise_model(year_a)
    epoch_model_b = get_epoch_noise_model(year_b)
    # Комбинируем модели (берем максимальный штраф)
    combined_epoch_model = {
        "geometric_sigma_multiplier": max(
            epoch_model_a["geometric_sigma_multiplier"],
            epoch_model_b["geometric_sigma_multiplier"],
        ),
        "texture_threshold_boost": max(
            epoch_model_a["texture_threshold_boost"],
            epoch_model_b["texture_threshold_boost"],
        ),
        "confidence_penalty": max(
            epoch_model_a["confidence_penalty"],
            epoch_model_b["confidence_penalty"],
        ),
    }
    
    # 4. Адаптивные априоры
    priors = _compute_adaptive_priors(summary_a, summary_b)
    
    # 5. Правдоподобия с учетом калибровки [FIX-11]
    # H0: Same person — геометрия должна быть близка
    # Используем зональный подход с калибровочными данными
    sigma_bone = 0.04 * combined_epoch_model["geometric_sigma_multiplier"]
    sigma_lig = 0.06 * combined_epoch_model["geometric_sigma_multiplier"]
    
    # [FIX-11] Если есть calibration_stats — используем их для более точного likelihood
    if calibration_stats:
        # Вычисляем likelihood по каждой зоне отдельно с учетом калибровки
        bucket = _determine_bucket_from_pose(pose_a)  # Используем bucket первого фото
        days_delta = abs(year_a - year_b) * 365
        
        # Калибровочный likelihood для bone зон
        bone_likelihood = 1.0
        bone_cal_meta = []
        for zone in ZONE_CATEGORIES["bone"]:
            if zone in zone_deltas:
                delta = zone_deltas[zone]
                lh, meta = compute_calibration_informed_likelihood(
                    delta, zone, calibration_stats, bucket, days_delta, combined_epoch_model
                )
                bone_likelihood *= lh
                bone_cal_meta.append(meta)
        
        # Калибровочный likelihood для ligament зон
        lig_likelihood = 1.0
        lig_cal_meta = []
        for zone in ZONE_CATEGORIES["ligament"]:
            if zone in zone_deltas:
                delta = zone_deltas[zone]
                lh, meta = compute_calibration_informed_likelihood(
                    delta, zone, calibration_stats, bucket, days_delta, combined_epoch_model
                )
                lig_likelihood *= lh
                lig_cal_meta.append(meta)
    else:
        # Fallback: взвешенное правдоподобие по категориям без калибровки
        bone_likelihood = math.exp(-(bone_delta_sum ** 2) / (2 * sigma_bone ** 2)) if bone_delta_sum > 0 else 1.0
        lig_likelihood = math.exp(-(ligament_delta_sum ** 2) / (2 * sigma_lig ** 2)) if ligament_delta_sum > 0 else 1.0
        bone_cal_meta = []
        lig_cal_meta = []
    
    # [FIX-9] Coverage penalty: если данных мало — понижаем уверенность
    coverage_penalty = max(0.3, coverage_ratio)
    
    # [FIX-34] Применяем confidence penalty от эпохи
    epoch_confidence = 1.0 - combined_epoch_model["confidence_penalty"]
    
    l_h0_geom = (bone_likelihood * 0.7 + lig_likelihood * 0.3) * coverage_penalty * epoch_confidence
    l_h2_geom = (1.0 - l_h0_geom) * coverage_penalty * epoch_confidence
    
    # [FIX-28, FIX-31, FIX-36] Longitudinal хронологический likelihood
    # Используем временную модель для проверки согласованности изменений
    chron_likelihood = 1.0
    chron_info = {"used": False, "consistent": True, "note": "No longitudinal model"}
    
    if longitudinal_model:
        chron_result = longitudinal_model.compute_chronological_likelihood(
            summary_a.get("photo_id"), summary_b.get("photo_id")
        )
        chron_likelihood = chron_result["likelihood"]
        chron_info = {
            "used": True,
            "consistent": chron_result.get("consistent", True),
            "year_delta": chron_result.get("year_delta", 0),
            "inconsistencies_count": len(chron_result.get("inconsistencies", [])),
            "note": chron_result.get("note", ""),
        }
    
    # Комбинируем геометрический и хронологический likelihood
    # Хронология особенно важна для H0 (same person)
    l_h0_combined = l_h0_geom * (0.7 + 0.3 * chron_likelihood)
    l_h2_combined = l_h2_geom * (0.9 + 0.1 * chron_likelihood)  # H2 меньше зависит от хронологии
    
    # 6. Байесовское обновление
    ev_h0 = priors["H0"] * l_h0_combined * (1.0 - l_h1_tex)
    ev_h1 = priors["H1"] * l_h1_tex
    ev_h2 = priors["H2"] * l_h2_combined * (1.0 - l_h1_tex)
    
    z = ev_h0 + ev_h1 + ev_h2 + 1e-9
    posteriors = {
        "H0": round(ev_h0 / z, 4),
        "H1": round(ev_h1 / z, 4),
        "H2": round(ev_h2 / z, 4),
    }
    
    # 7. Хронология и поза (year_a, year_b уже определены выше [FIX-34])
    delta_years = abs(year_a - year_b)
    
    yaw_a = abs(pose_a.get("yaw", 0.0))
    yaw_b = abs(pose_b.get("yaw", 0.0))
    # [FIX-10] Точнее: в градусах, не нормированное на 180
    pose_distance_deg = abs(yaw_a - yaw_b)
    mutual_vis = max(0.0, 1.0 - pose_distance_deg / 90.0)  # >90° = низкая видимость
    
    # Флаги исключённых зон
    excluded_count = len(excluded_zones)
    
    # 8. Вердикт с учётом coverage и uncertainty [FIX-10, FIX-100]
    # Вероятностный вывод вместо жёстких порогов (>0.6, >0.5)
    
    # Вычисляем confidence и uncertainty
    max_posterior = max(posteriors["H0"], posteriors["H1"], posteriors["H2"])
    second_max = sorted([posteriors["H0"], posteriors["H1"], posteriors["H2"]], reverse=True)[1]
    
    # Confidence = насколько dominant гипотеза (margin от второй)
    confidence = max_posterior - second_max
    
    # Uncertainty = entropy нормированная (0 = уверены, 1 = полная неопределенность)
    entropy = -sum(p * math.log(p + 1e-10) for p in posteriors.values())
    max_entropy = math.log(3)  # Максимальная энтропия для 3 гипотез
    uncertainty = entropy / max_entropy
    
    # Решение о вердикте с учетом uncertainty
    # Вместо жёстких порогов используем adaptивную логику
    
    # Определяем dominant гипотезу
    dominant = max(posteriors, key=posteriors.get)
    dominant_posterior = posteriors[dominant]
    
    # Пороги зависят от uncertainty и coverage
    # При высокой неопределенности повышаем требования к dominant
    if coverage_ratio < 0.5:
        verdict = "INSUFFICIENT_DATA"
        verdict_confidence = 0.0
    elif uncertainty > 0.7:
        # Высокая неопределенность — требуем очень высокий posterior
        if dominant_posterior > 0.75 and confidence > 0.4:
            verdict = dominant
            verdict_confidence = confidence * (1 - uncertainty)
        else:
            verdict = "INSUFFICIENT_DATA"
            verdict_confidence = 0.0
    elif uncertainty > 0.5:
        # Средняя неопределенность — требуем высокий posterior
        if dominant_posterior > 0.65 and confidence > 0.25:
            verdict = dominant
            verdict_confidence = confidence * (1 - uncertainty)
        else:
            verdict = "INSUFFICIENT_DATA"
            verdict_confidence = 0.0
    else:
        # Низкая неопределенность — стандартные требования
        if dominant_posterior > 0.55 and confidence > 0.15:
            verdict = dominant
            verdict_confidence = confidence * (1 - uncertainty)
        else:
            verdict = "INSUFFICIENT_DATA"
            verdict_confidence = 0.0
    
    # Дополнительная проверка: если H0 и H2 близки (возможная подмена)
    if verdict != "INSUFFICIENT_DATA" and abs(posteriors["H0"] - posteriors["H2"]) < 0.15:
        if posteriors["H1"] > 0.2:  # H1 имеет значительную вероятность
            verdict = "H1"  # Подозрение на синтетику
            verdict_confidence = confidence * 0.7  # Снижаем confidence
    
    # [FIX-9] Computation log для traceability и explainability
    # [FIX-34] Добавляем информацию об эпохах и калибровке
    # [FIX-82] Добавляем информацию о версиях методологий
    computation_log = [
        f"Methodology: {METHODOLOGY_VERSION}",
        f"Photo A method: {method_a}, Photo B method: {method_b}",
    ]
    
    # [FIX-82] Предупреждение если версии отличаются
    if method_a != method_current or method_b != method_current:
        computation_log.append(f"WARN: Methodology version mismatch — current={method_current}, A={method_a}, B={method_b}")
    
    computation_log.extend([
        f"Years: {year_a} (epoch mult: {epoch_model_a['geometric_sigma_multiplier']:.1f}) vs {year_b} ({epoch_model_b['geometric_sigma_multiplier']:.1f})",
        f"Combined epoch penalty: {combined_epoch_model['confidence_penalty']:.0%}",
        f"Calibration used: {'yes' if calibration_stats else 'no'}",
        f"Zones analyzed: {len(zone_deltas)}/{len(ZONE_WEIGHTS)} (coverage: {coverage_ratio:.1%})",
        f"Zones excluded due to expression: {excluded_count} ({', '.join(excluded_zones) if excluded_zones else 'none'})",
        f"Missing metrics A: {len(missing_a)} zones, B: {len(missing_b)} zones",
        f"Adaptive priors: H0={priors['H0']:.3f}, H1={priors['H1']:.3f}, H2={priors['H2']:.3f}",
        f"Structural SNR: {structural_snr:.2f} dB",
        f"Bone divergence: {bone_delta_sum:.3f}, Ligament: {ligament_delta_sum:.3f}",
        f"Bone likelihood: {bone_likelihood:.3f}, Lig likelihood: {lig_likelihood:.3f}",
        f"Texture H1 raw composite: {h1_texture.get('raw_composite', 0):.3f}",
        f"Texture H1 natural score: {h1_texture.get('naturalScore', 0):.3f}",
        f"Texture H1 adjusted: {h1_texture['composite_score']:.3f}, likelihood: {l_h1_tex:.3f}",
        f"H1 subtype: {h1_subtype['primary']} (confidence: {h1_subtype['confidence']:.2f}, indicators: {', '.join(h1_subtype['indicators']) if h1_subtype['indicators'] else 'none'})",
        f"Pose distance: {pose_distance_deg:.1f}°, mutual visibility: {mutual_vis:.2f}",
        f"Time delta: {delta_years} years",
        f"Coverage penalty applied: {coverage_penalty:.2f}",
    ])
    
    # [FIX-28,31,36] Добавляем longitudinal информацию в лог
    if chron_info["used"]:
        computation_log.extend([
            f"Longitudinal model: used",
            f"Chronological consistency: {chron_info['consistent']}",
            f"Chronological likelihood: {chron_likelihood:.3f}",
        ])
        if chron_info.get("inconsistencies_count", 0) > 0:
            computation_log.append(f"WARN: {chron_info['inconsistencies_count']} chronological inconsistencies detected")
    else:
        computation_log.append("Longitudinal model: not available")
    
    computation_log.extend([
        f"Final posteriors: H0={posteriors['H0']:.3f}, H1={posteriors['H1']:.3f}, H2={posteriors['H2']:.3f}",
        f"Verdict: {verdict}",
    ])
    
    # Результат с полной структурой и traceability
    return {
        "aId": summary_a.get("photo_id"),
        "bId": summary_b.get("photo_id"),
        "geometric": {
            "snr": round(structural_snr, 2),
            "boneScore": round(max(0, 1.0 - bone_delta_sum), 3),
            "ligamentScore": round(max(0, 1.0 - ligament_delta_sum), 3),
            "softTissueScore": round(max(0, 1.0 - soft_delta_sum), 3),
            "zoneCount": len(zone_deltas),
            "excludedZones": list(excluded_zones),
            "categoryDivergence": {k: round(v, 3) for k, v in category_divergence.items()},
        },
        "texture": {
            "syntheticProb": round(h1_texture["composite_score"], 3),
            "rawSyntheticProb": round(h1_texture.get("raw_composite", h1_texture["composite_score"]), 3),
            "naturalScore": round(h1_texture.get("naturalScore", 0), 3),
            "fft": round(float(tex_a.get("fft_high_freq_ratio", 0.5)), 3),
            "lbp": round(float(tex_a.get("lbp_complexity", 0.5)), 3),
            "albedo": round(float(tex_a.get("albedo_uniformity", 0.5)), 3),
            "specular": round(float(tex_a.get("specular_gloss", 0.5)), 3),
            "textureFeatures": h1_texture["features"],
            "naturalMarkers": h1_texture.get("naturalMarkers", {}),
            "epochAdjustments": h1_texture.get("epochAdjustments", {}),
            "h1Subtype": h1_subtype,  # [FIX-19] Классификация подтипа синтетики
        },
        "chronology": {
            "deltaYears": delta_years,
            "boneJump": round(bone_delta_sum, 3),
            "ligamentJump": round(ligament_delta_sum, 3),
            "flags": ["POSSIBLE_AGING"] if delta_years > 5 else [],
            # [FIX-28,31,36] Расширенная хронологическая информация
            "longitudinal": {
                "modelUsed": chron_info["used"],
                "consistent": chron_info.get("consistent", True),
                "chronologicalLikelihood": round(chron_likelihood, 3) if chron_info["used"] else None,
                "inconsistenciesCount": chron_info.get("inconsistencies_count", 0),
                "note": chron_info.get("note", ""),
            } if chron_info["used"] else {"modelUsed": False},
        },
        "pose": {
            "mutualVisibility": round(mutual_vis, 2),
            "expressionExcluded": excluded_count,
            "poseDistanceDeg": round(pose_distance_deg, 1),
        },
        "dataQuality": {
            "coverageRatio": round(coverage_ratio, 2),
            "missingZonesA": missing_a,
            "missingZonesB": missing_b,
        },
        "likelihoods": {
            "H0": round(l_h0_combined, 3),
            "H1": round(l_h1_tex, 3),
            "H2": round(l_h2_combined, 3),
            "chronological": round(chron_likelihood, 3) if chron_info["used"] else None,
            "components": {
                "geometricH0": round(l_h0_geom, 3),
                "geometricH2": round(l_h2_geom, 3),
                "textureH1": round(l_h1_tex, 3),
            },
        },
        "priors": {k: round(v, 4) for k, v in priors.items()},
        "posteriors": posteriors,
        "verdict": verdict,
        "methodologyVersion": METHODOLOGY_VERSION,
        "computationLog": computation_log,
    }




class LegacyRuntime:
    def __init__(self) -> None:
        self.pose_detector = PoseDetector(device="cpu")
        self.reconstruction = ReconstructionAdapter(device="cpu", detector_device="cpu")
        self.texture = SkinTextureAnalyzer()
        self.quality = QualityGate(
            blur_threshold=SETTINGS.blur_threshold,
            noise_threshold=SETTINGS.noise_threshold,
        )
        if _UV_AVAILABLE and HDUVConfig is not None and HDUVTextureGenerator is not None:
            self.uv = HDUVTextureGenerator(
                HDUVConfig(
                    uv_size=768,
                    super_sample=1,
                    verbose=False,
                    enable_delighting=False,
                )
            )
        else:
            self.uv = None  # UV module not available in this environment


def get_runtime() -> LegacyRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = LegacyRuntime()
        return _RUNTIME


def _zone_indices(zone_name: str) -> np.ndarray:
    return np.fromiter(MACRO_BONE_INDICES.get(zone_name, []), dtype=np.int64)


def _zone_centroid(vertices: np.ndarray, zone_name: str) -> np.ndarray:
    idx = _zone_indices(zone_name)
    if idx.size == 0:
        return np.zeros(3, dtype=np.float32)
    idx = idx[(idx >= 0) & (idx < vertices.shape[0])]
    if idx.size == 0:
        return np.zeros(3, dtype=np.float32)
    return np.mean(vertices[idx], axis=0)


def _normalize_vertices(vertices: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
    """
    [STAB-01] Робастная нормализация.
    Используем межскуловое расстояние (Zygomatic Breadth) как наиболее стабильную костную базу.
    Это исключает влияние прически, головных уборов и мимики на масштаб модели.
    """
    centered = np.asarray(vertices, dtype=np.float32) - np.mean(vertices, axis=0, keepdims=True)
    
    # Извлекаем центроиды скул для масштаба
    cheek_L = np.mean(centered[list(MACRO_BONE_INDICES['cheekbone_L'])], axis=0)
    cheek_R = np.mean(centered[list(MACRO_BONE_INDICES['cheekbone_R'])], axis=0)
    zygomatic_breadth = float(np.linalg.norm(cheek_L - cheek_R)) or 1e-6
    
    normalized = centered / zygomatic_breadth
    return normalized, {
        "stable_scale": zygomatic_breadth,
        "zygomatic_breadth": zygomatic_breadth,
    }


def _assess_reconstruction_trust(recon: ReconstructionResult) -> dict[str, Any]:
    """
    [FIX-48] Проверка доверия к 3D-реконструкции перед использованием метрик.
    
    Returns:
        {
            "trust_score": float (0-1),
            "is_usable": bool,
            "issues": list[str],
            "vertex_quality": float,
            "confidence_metrics": dict,
        }
    """
    issues = []
    
    # 1. Проверяем количество вершин
    vertex_count = len(recon.vertices_world)
    if vertex_count < 1000:
        issues.append(f"Too few vertices: {vertex_count}")
        vertex_quality = 0.3
    elif vertex_count < 3000:
        issues.append(f"Low vertex count: {vertex_count}")
        vertex_quality = 0.6
    else:
        vertex_quality = 1.0
    
    # 2. Проверяем качество позы
    pose_confidence = getattr(recon, 'pose_confidence', 0.8)
    if pose_confidence < 0.5:
        issues.append(f"Low pose confidence: {pose_confidence:.2f}")
    
    # 3. Проверяем параметры трансформации
    trans_params = getattr(recon, 'trans_params', None)
    if trans_params is None:
        issues.append("Missing transformation parameters")
        transform_quality = 0.0
    else:
        # Проверяем масштаб (scale) - должен быть разумным
        scale = float(trans_params.get('scale', 1.0) if isinstance(trans_params, dict) else 1.0)
        if scale < 0.3 or scale > 3.0:
            issues.append(f"Abnormal scale: {scale:.2f}")
            transform_quality = 0.5
        else:
            transform_quality = 1.0
    
    # 4. Проверяем углы (не должны быть экстремальными)
    angles = getattr(recon, 'angles_deg', None)
    if angles is not None:
        yaw, pitch, roll = angles if len(angles) >= 3 else (0, 0, 0)
        if abs(yaw) > 60:
            issues.append(f"Extreme yaw: {yaw:.1f}°")
        if abs(pitch) > 45:
            issues.append(f"Extreme pitch: {pitch:.1f}°")
    
    # 5. Комбинированный trust score
    trust_score = (
        vertex_quality * 0.4 +
        pose_confidence * 0.3 +
        transform_quality * 0.3
    )
    
    # Критичные проблемы снижают trust резко
    if len(issues) >= 2:
        trust_score *= 0.7
    if len(issues) >= 3:
        trust_score *= 0.5
    
    # Минимальный порог для использования
    is_usable = trust_score > 0.4 and vertex_quality > 0.3
    
    return {
        "trust_score": round(trust_score, 3),
        "is_usable": is_usable,
        "issues": issues,
        "vertex_quality": round(vertex_quality, 3),
        "confidence_metrics": {
            "vertex_count": vertex_count,
            "pose_confidence": pose_confidence,
            "transform_quality": transform_quality,
        },
    }


def _compute_geometry_metrics(recon: ReconstructionResult, bucket: str) -> tuple[dict[str, float], float]:
    # [FIX-48] Проверяем доверие к реконструкции
    trust_assessment = _assess_reconstruction_trust(recon)
    
    if not trust_assessment["is_usable"]:
        # Возвращаем пустые метрики с низкой reliability
        return {}, 0.2
    
    # Trust score влияет на reliability
    trust_penalty = 1.0 - trust_assessment["trust_score"]
    
    metrics, reliability = extract_macro_bone_metrics(recon.vertices_world, MACRO_BONE_INDICES, recon.angles_deg)
    
    # Снижаем reliability на основе trust
    reliability *= trust_assessment["trust_score"]
    
    # [ITER-1] Структурные маркеры с учетом позы
    asymmetry = compute_asymmetry_vector(recon.vertices_world, bucket)
    ligaments = compute_ligament_distances(recon.vertices_world, bucket)
    
    # [ITER-2] Объемные показатели
    volumes = compute_volume_indices(recon.vertices_world, bucket)
    
    metrics.update(asymmetry)
    metrics.update(ligaments)
    metrics.update(volumes)
    
    # Добавляем trust-метрики для explainability
    metrics["_reconstruction_trust_score"] = trust_assessment["trust_score"]
    metrics["_reconstruction_issues_count"] = len(trust_assessment["issues"])
    
    return metrics, reliability


def compute_asymmetry_vector(vertices: np.ndarray, bucket: str) -> dict[str, float]:
    """
    [ITER-1.2] Вектор костной асимметрии.
    Рассчитывается только в фронтальном ракурсе.
    """
    if bucket != 'frontal':
        return {}
    
    # Углы челюсти
    jaw_L = _zone_centroid(vertices, 'jaw_angle_L')
    jaw_R = _zone_centroid(vertices, 'jaw_angle_R')
    
    # Орбиты
    orbit_L = _zone_centroid(vertices, 'orbit_L')
    orbit_R = _zone_centroid(vertices, 'orbit_R')
    
    # Вектор перекоса (разница высот)
    jaw_skew = abs(jaw_L[1] - jaw_R[1])
    orbit_skew = abs(orbit_L[1] - orbit_R[1])
    
    return {
        "asymmetry_jaw_skew": float(jaw_skew),
        "asymmetry_orbit_skew": float(orbit_skew),
        "asymmetry_total_vector": float(jaw_skew + orbit_skew)
    }


def compute_ligament_distances(vertices: np.ndarray, bucket: str) -> dict[str, float]:
    """
    [ITER-1.2] Дистанция до связочных якорей.
    Проверяет видимость зоны перед расчетом.
    """
    metrics = {}
    
    # Скуловая связка (Zygomatic Ligament)
    if 'left' in bucket or bucket == 'frontal':
        l_zyg_L = _zone_centroid(vertices, 'ligament_zygomatic_L')
        metrics['ligament_zygomatic_L_depth'] = float(l_zyg_L[2])
        
    if 'right' in bucket or bucket == 'frontal':
        l_zyg_R = _zone_centroid(vertices, 'ligament_zygomatic_R')
        metrics['ligament_zygomatic_R_depth'] = float(l_zyg_R[2])
        
    return metrics


def compute_volume_indices(vertices: np.ndarray, bucket: str) -> dict[str, float]:
    """
    [ITER-2.1] Индексы объема и дефицита тканей.
    """
    metrics = {}
    
    # 1. Neurocranium (Ширина лба к височным ямкам) - только фронтально
    if bucket == 'frontal':
        temp_L = _zone_centroid(vertices, 'temporal_L')
        temp_R = _zone_centroid(vertices, 'temporal_R')
        metrics['index_neurocranium_width'] = float(np.linalg.norm(temp_L - temp_R))
        
    # 2. Facial BMI (Выпуклость щек) - только профили
    if 'profile' in bucket:
        # Для профиля берем только видимую сторону
        side = 'L' if 'left' in bucket else 'R'
        cheek_bone = _zone_centroid(vertices, f'cheekbone_{side}')
        cheek_soft = _zone_centroid(vertices, f'cheek_soft_{side}')
        # Проекция разницы на ось Z (глубина)
        metrics[f'facial_bmi_{side}'] = float(cheek_soft[2] - cheek_bone[2])
        
    return metrics



def _transform_vertices_2d_to_original(vertices_2d_224: np.ndarray, trans_params: np.ndarray) -> np.ndarray:
    """
    [PIPE-FIX] Transform vertices_2d from 3DDFA's 224x224 crop space
    to original image coordinates, matching the 3DDFA model's own
    extractTexNew logic (recon.py lines 636-638).

    Steps (same as 3DDFA's back_resize_ldms):
      1. Flip Y: image Y is top-down, 3DDFA crop Y is bottom-up
      2. Add crop offset (left, up)
      3. Scale back to original image dimensions
    """
    v2d = vertices_2d_224.copy()
    target_size = 224

    # Step 1: Flip Y (3DDFA crop convention: Y=0 at bottom)
    v2d[:, 1] = target_size - 1 - v2d[:, 1]

    # Step 2-3: back_resize_ldms logic
    w0, h0, s = float(trans_params[0]), float(trans_params[1]), float(trans_params[2])
    cx, cy = float(trans_params[3]), float(trans_params[4])

    w = int(w0 * s)
    h = int(h0 * s)
    left = int(w / 2 - target_size / 2 + (cx - w0 / 2) * s)
    up = int(h / 2 - target_size / 2 + (h0 / 2 - cy) * s)

    v2d[:, 0] = (v2d[:, 0] + left) / w * w0
    v2d[:, 1] = (v2d[:, 1] + up) / h * h0

    return v2d


def _recon_dict(reconstruction: Any) -> dict[str, Any]:
    # [PIPE-FIX] Transform vertices_2d from 224x224 crop space to original image coords.
    # Without this, the UV baker samples from the wrong part of the image (black background).
    # This matches 3DDFA's own extractTexNew logic (recon.py lines 636-638):
    #   1. Flip Y: v2d[:, 1] = 224 - 1 - v2d[:, 1]
    #   2. back_resize_ldms to original image coordinates
    v2d_224 = reconstruction.vertices_image[:, :2]
    tp = reconstruction.trans_params
    if tp is not None:
        v2d_orig = _transform_vertices_2d_to_original(v2d_224, tp)
    else:
        v2d_orig = v2d_224

    return {
        "triangles": reconstruction.triangles,
        "uv_coords": reconstruction.uv_coords,
        "vertices": reconstruction.vertices_world,  # [SYS-08] Required by UV generator
        "vertices_2d": v2d_orig,
        "vertices_3d": reconstruction.vertices_camera,
        "visible_idx_renderer": reconstruction.visible_idx_renderer,
        "angles_deg": reconstruction.angles_deg,
    }


def _save_small_render_images(raw_result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    artifacts: dict[str, str] = {}

    def _save_rgb(name: str, value: Any) -> None:
        arr = np.asarray(value)
        if arr.ndim == 4:
            arr = arr[0]
        arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        target = output_dir / f"{name}.png"
        cv2.imwrite(str(target), bgr)
        artifacts[name] = target.name

    def _save_mask(name: str, value: Any) -> None:
        arr = np.asarray(value)
        if arr.ndim == 4:
            arr = arr[0, :, :, 0]
        elif arr.ndim == 3 and arr.shape[-1] == 1:
            arr = arr[:, :, 0]
        arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        target = output_dir / f"{name}.png"
        cv2.imwrite(str(target), arr)
        artifacts[name] = target.name

    _save_rgb("render_face", raw_result["render_face"])
    _save_rgb("render_shape", raw_result["render_shape"])
    _save_mask("render_mask", raw_result["render_mask"])
    return artifacts


def _save_face_crop(image_bgr: np.ndarray, reconstruction: Any, output_dir: Path) -> str:
    """
    [FIX-12, FIX-13] Skin-only face crop с улучшенной soft-маской и PNG для forensic-качества.
    
    Исправления:
    - Плавный (soft) порог вместо жёсткого > 0.5 для сглаживания границ
    - Альфа-канал с весами маски для текстурного анализа
    - PNG вместо JPEG (без потерь) для сохранения высокочастотных деталей
    """
    seg_visible = reconstruction.payload.get("seg_visible")
    trans_params = reconstruction.trans_params
    if seg_visible is None or trans_params is None:
        return ""

    h, w = image_bgr.shape[:2]

    # 3DDFA seg channels: [right_eye, left_eye, right_eyebrow, left_eyebrow, nose, up_lip, down_lip, skin]
    skin_224 = seg_visible[:, :, 7].copy()
    
    # [FIX-12] Плавное исключение частей лица вместо жёсткого порога > 0.5
    # Используем smooth step function: (1 - sigmoid((x - 0.5) * 10))
    for i in [0, 1, 2, 3, 5, 6]:  # eyes, eyebrows, lips
        part_mask = seg_visible[:, :, i]
        # Soft weight: чем выше confidence части, тем меньше вес кожи
        # sigmoid даёт плавный переход около порога 0.5
        exclusion_weight = 1.0 / (1.0 + np.exp(-10 * (part_mask - 0.5)))
        skin_224 *= (1.0 - exclusion_weight)
    
    # Нормализуем маску к [0, 255] с сохранением плавных границ
    skin_224_uint8 = np.clip(skin_224 * 255, 0, 255).astype(np.uint8)

    # Project from 224x224 to original image using back_resize_crop_img
    try:
        sys.path.insert(0, str(REPO_ROOT / "core" / "3ddfa_v3"))
        from util.io import back_resize_crop_img
        from PIL import Image as PILImage

        # [FIX-12] Сохраняем grayscale маску с плавными границами
        mask_rgb = np.stack((skin_224_uint8, skin_224_uint8, skin_224_uint8), axis=-1)
        blank = np.zeros((h, w, 3), dtype=np.uint8)
        full_mask_rgb = back_resize_crop_img(mask_rgb, trans_params, blank, resample_method=PILImage.BILINEAR)
        mask = full_mask_rgb[:, :, 0]
    except Exception:
        # Fallback с BILINEAR для плавности
        mask = cv2.resize(skin_224_uint8, (w, h), interpolation=cv2.INTER_LINEAR)

    # Find bounding box of mask (порог 10 для отсечения слабых хвостов)
    coords = cv2.findNonZero((mask > 10).astype(np.uint8))
    if coords is None:
        return ""

    x, y, bw, bh = cv2.boundingRect(coords)
    pad_x = int(bw * 0.15)
    pad_y = int(bh * 0.15)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(w, x + bw + pad_x)
    y2 = min(h, y + bh + pad_y)

    # [FIX-13] Создаём RGBA изображение с альфа-каналом вместо маскирования
    # Это сохраняет исходные пиксели + веса для текстурного анализа
    bgra = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = mask  # Alpha channel = mask weight
    
    # Обрезаем
    face_crop_rgba = bgra[y1:y2, x1:x2]
    
    # [FIX-13] PNG вместо JPEG для forensic-качества (без артефактов сжатия)
    target_png = output_dir / "face_crop.png"
    cv2.imwrite(str(target_png), face_crop_rgba)
    
    # Также сохраняем JPEG для совместимости с legacy (качество 98)
    face_crop_rgb = cv2.cvtColor(face_crop_rgba, cv2.COLOR_BGRA2BGR)
    target_jpg = output_dir / "face_crop.jpg"
    cv2.imwrite(str(target_jpg), face_crop_rgb, [int(cv2.IMWRITE_JPEG_QUALITY), 98])
    
    return target_jpg.name


def _save_uv_assets(image_bgr: np.ndarray, reconstruction: Any, output_dir: Path) -> dict[str, str]:
    runtime = get_runtime()
    _uv_tex_analysis, uv_tex_beauty, _uv_mask, uv_conf, _aux = runtime.uv.generate(image_bgr, _recon_dict(reconstruction))
    texture_path = output_dir / "uv_texture.png"
    conf_path = output_dir / "uv_confidence.png"
    cv2.imwrite(str(texture_path), uv_tex_beauty)
    conf_uint8 = np.clip(uv_conf * 255.0, 0, 255).astype(np.uint8)
    cv2.imwrite(str(conf_path), conf_uint8)
    return {
        "uv_texture": texture_path.name,
        "uv_confidence": conf_path.name,
    }


def _save_mesh_assets(reconstruction: Any, texture_filename: str, output_dir: Path) -> dict[str, str]:
    obj_path = output_dir / "mesh.obj"
    mtl_path = output_dir / "mesh.mtl"
    vertices = reconstruction.vertices_world
    normals = reconstruction.normals_world
    uv_coords = reconstruction.uv_coords
    triangles = reconstruction.triangles

    mtl_path.write_text(
        "\n".join(
            [
                "newmtl FaceMaterial",
                "Ka 1.000 1.000 1.000",
                "Kd 1.000 1.000 1.000",
                "Ks 0.000 0.000 0.000",
                f"map_Kd {texture_filename}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with obj_path.open("w", encoding="utf-8") as handle:
        handle.write("mtllib mesh.mtl\n")
        handle.write("usemtl FaceMaterial\n")
        for vertex in vertices:
            handle.write(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}\n")
        if uv_coords is not None:
            for uv in uv_coords:
                handle.write(f"vt {uv[0]:.6f} {1.0 - uv[1]:.6f}\n")
        for normal in normals:
            handle.write(f"vn {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}\n")
        for triangle in triangles:
            a, b, c = (int(index) + 1 for index in triangle.tolist())
            handle.write(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n")

    return {"mesh_obj": obj_path.name, "mesh_mtl": mtl_path.name}


def extract_photo_bundle(
    source_path: Path,
    dataset: str,
    photo_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    runtime = get_runtime()
    ensure_directory(output_dir)

    image_bgr = cv2.imread(str(source_path))
    if image_bgr is None:
        raise RuntimeError(f"Не удалось прочитать изображение: {source_path}")

    pose = runtime.pose_detector.get_pose(source_path)
    bucket = str(pose.get("bucket", "unclassified"))
    angle = RAW_BUCKET_TO_UI.get(bucket, "unknown")

    reconstruction = resolve_reconstruction(
        runtime.reconstruction,
        source_path,
        output_dir,
        neutral_expression=False,
    )

    raw_result = reconstruction.payload.get("raw_result", {})
    # [PIPE-FIX] Skip render_face/render_shape/render_mask — not needed for pipeline.
    # Only extract UV texture, mask, confidence, mesh, and face crop (like v2 script).
    uv_artifacts = _save_uv_assets(image_bgr, reconstruction, output_dir) if runtime.uv else {}
    mesh_artifacts = _save_mesh_assets(reconstruction, uv_artifacts.get("uv_texture", "uv_texture.png"), output_dir) if uv_artifacts else {}

    # Build face crop from seg_visible (like v2 script's apply_segmentation_mask)
    face_crop_name = _save_face_crop(image_bgr, reconstruction, output_dir)

    # Copy original photo to output directory for UI use
    import shutil
    original_copy_name = source_path.name
    shutil.copy2(source_path, output_dir / original_copy_name)

    # Texture analysis on face_crop.jpg (like v2 script — masked crop, no separate mask needed)
    face_crop_path = output_dir / face_crop_name if face_crop_name else None
    texture_forensics = runtime.texture.analyze_image(face_crop_path or source_path, None)
    quality = runtime.quality.evaluate(source_path)
    geometry_metrics, pose_reliability = _compute_geometry_metrics(reconstruction, bucket)


    # Итоговый вес достоверности: текстурная четкость * геометрическая стабильность (поза)
    final_reliability = float(texture_forensics.get("reliability_weight", 1.0)) * pose_reliability

    metrics = {
        **geometry_metrics,
        "reliability_weight": final_reliability,
        "texture_lbp_complexity": float(texture_forensics.get("lbp_complexity", 0.0)),
        "texture_lbp_uniformity": float(texture_forensics.get("lbp_uniformity", 0.0)),
        "texture_specular_gloss": float(texture_forensics.get("specular_gloss", 0.0)),
        "texture_max_reflectance": float(texture_forensics.get("max_reflectance", 0.0)),
        "texture_silicone_prob": float(texture_forensics.get("silicone_probability", 0.0)),
        "texture_pore_density": float(texture_forensics.get("pore_density", 0.0)),
        "texture_spot_density": float(texture_forensics.get("spot_density", 0.0)),
        "texture_wrinkle_forehead": float(texture_forensics.get("wrinkle_forehead", 0.0)),
        "texture_wrinkle_nasolabial": float(texture_forensics.get("wrinkle_nasolabial", 0.0)),
        "texture_global_smoothness": float(texture_forensics.get("global_smoothness", 0.0)),
    }

    # [FIX-82, FIX-83, FIX-95] Версионирование и lineage для traceability
    # Строим lineage доказательств
    lineage = {
        "raw_sources": {
            "original_image": str(source_path),
            "file_size_bytes": source_path.stat().st_size,
            "file_hash": None,  # Можно добавить SHA256 при необходимости
        },
        "extraction_steps": [
            {"step": "pose_detection", "source": pose.get("pose_source", "unknown"), "timestamp": iso_now()},
            {"step": "3d_reconstruction", "method": "3DDFA_v3", "timestamp": iso_now()},
            {"step": "texture_analysis", "input": face_crop_name or "original", "timestamp": iso_now()},
            {"step": "quality_assessment", "timestamp": iso_now()},
            {"step": "geometry_metrics", "bucket": bucket, "timestamp": iso_now()},
        ],
        "methodology_version": METHODOLOGY_VERSION,
        "artifact_version": ARTIFACT_VERSION,
    }
    
    # Определяем статус с учетом quality и pose reliability [FIX-84]
    # Различаем missing / not_applicable / low_quality явно
    quality_flags = quality.get("flags", {}) if isinstance(quality, dict) else {}
    status_detail = {
        "overall": "ready",
        "quality_status": "ok" if quality.get("overall_score", 0) > 0.5 else "low_quality",
        "pose_status": "ok" if not pose.get("needs_manual_review", False) else "uncertain",
        "reliability_tier": "high" if final_reliability > 0.8 else ("medium" if final_reliability > 0.5 else "low"),
        "usable_for_comparison": final_reliability > 0.5 and quality.get("overall_score", 0) > 0.5,
    }
    
    summary = {
        "photo_id": photo_id,
        "dataset": dataset,
        "filename": source_path.name,
        "source_path": str(source_path),
        "file_size_bytes": source_path.stat().st_size,
        "bucket": bucket,
        "angle": angle,
        "bucket_label": angle,
        "pose": {
            "yaw": float(pose.get("yaw", 0.0)),
            "pitch": float(pose.get("pitch", 0.0)),
            "roll": float(pose.get("roll", 0.0)),
            "bucket": bucket,
            "pose_source": pose.get("pose_source"),
            "needs_manual_review": bool(pose.get("needs_manual_review", False)),
        },
        "reconstruction": {
            "angles_deg": [float(value) for value in np.asarray(reconstruction.angles_deg).reshape(-1).tolist()],
            "vertex_count": int(reconstruction.vertices_world.shape[0]),
            "triangle_count": int(reconstruction.triangles.shape[0]),
        },
        "quality": quality,
        "texture_forensics": texture_forensics,
        "metrics": metrics,
        "selected_metric_keys": BUCKET_METRIC_KEYS.get(bucket, BUCKET_METRIC_KEYS["unclassified"]),
        "artifacts": {
            **uv_artifacts,
            **mesh_artifacts,
            "original_photo": original_copy_name,
        },
        "status": "ready" if status_detail["usable_for_comparison"] else "needs_review",
        "status_detail": status_detail,  # [FIX-84] Развернутый статус
        "lineage": lineage,  # [FIX-87, FIX-96] Полная trace-цепочка
        "extracted_at": iso_now(),
        "artifact_version": ARTIFACT_VERSION,
        "methodology_version": METHODOLOGY_VERSION,  # [FIX-95] Версия методики
        "runtime_config_hash": ForensicManifest.compute_manifest_id(photo_id, runtime),
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def recompute_metric_subset(
    source_path: Path,
    dataset: str,
    photo_id: str,
    output_dir: Path,
    metric_keys: list[str],
) -> dict[str, Any]:
    summary = read_json(output_dir / "summary.json", {})
    if not summary:
        return extract_photo_bundle(source_path, dataset, photo_id, output_dir)

    runtime = get_runtime()
    reconstruction = resolve_reconstruction(
        runtime.reconstruction,
        source_path,
        output_dir,
        neutral_expression=False,
    )
    bucket = summary.get("bucket", "unclassified")
    geometry_metrics, pose_reliability = _compute_geometry_metrics(reconstruction, bucket)


    needs_texture = any(key.startswith("texture_") for key in metric_keys)
    texture_forensics = summary.get("texture_forensics", {})
    quality = summary.get("quality", {})
    if needs_texture:
        mask_name = summary.get("artifacts", {}).get("render_mask")
        mask_path = output_dir / mask_name if isinstance(mask_name, str) else None
        texture_forensics = runtime.texture.analyze_image(source_path, mask_path)
    
    final_reliability = float(texture_forensics.get("reliability_weight", 1.0)) * pose_reliability

    if any(key in {"blur_variance", "noise_level"} for key in metric_keys):
        quality = runtime.quality.evaluate(source_path)

    texture_metrics = {
        "reliability_weight": final_reliability,
        "texture_lbp_complexity": float(texture_forensics.get("lbp_complexity", 0.0)),
        "texture_lbp_uniformity": float(texture_forensics.get("lbp_uniformity", 0.0)),
        "texture_specular_gloss": float(texture_forensics.get("specular_gloss", 0.0)),
        "texture_max_reflectance": float(texture_forensics.get("max_reflectance", 0.0)),
        "texture_silicone_prob": float(texture_forensics.get("silicone_probability", 0.0)),
        "texture_pore_density": float(texture_forensics.get("pore_density", 0.0)),
        "texture_spot_density": float(texture_forensics.get("spot_density", 0.0)),
        "texture_wrinkle_forehead": float(texture_forensics.get("wrinkle_forehead", 0.0)),
        "texture_wrinkle_nasolabial": float(texture_forensics.get("wrinkle_nasolabial", 0.0)),
        "texture_global_smoothness": float(texture_forensics.get("global_smoothness", 0.0)),
    }

    merged_metrics = {**summary.get("metrics", {})}
    available_metrics = {**geometry_metrics, **texture_metrics}
    for key in metric_keys:
        if key in available_metrics:
            merged_metrics[key] = available_metrics[key]
        elif key == "blur_variance":
            merged_metrics[key] = float(quality.get("blur_variance", 0.0))
        elif key == "noise_level":
            merged_metrics[key] = float(quality.get("noise_level", 0.0))

    summary["metrics"] = merged_metrics
    summary["quality"] = quality
    summary["texture_forensics"] = texture_forensics
    summary["updated_at"] = iso_now()
    summary["artifact_version"] = ARTIFACT_VERSION
    summary["runtime_config_hash"] = ForensicManifest.compute_manifest_id(photo_id, runtime)
    write_json(output_dir / "summary.json", summary)
    return summary
