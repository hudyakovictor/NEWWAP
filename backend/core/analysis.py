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
from backend.core.longitudinal import LongitudinalModel
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
    ZONE_WEIGHTS,
)
from .utils import (
    BUCKET_METRIC_KEYS,
    RAW_BUCKET_TO_UI,
    ForensicManifest,
    compute_linear_snr,
    ensure_directory,
    iso_now,
    parse_date_from_name,
    fallback_date_for_file,
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

    [ITER-1] ИСПРАВЛЕНИЕ: Убраны преобразования в децибелы (log10).
    Теперь SNR всегда в линейной шкале для корректного сравнения с порогами.
    """
    if not zone_deltas:
        return 0.0

    # Взвешенное среднее отклонений
    # [FIX-C4] Нет дефолта 0.5 — зона без веса игнорируется (вес 0)
    weighted_delta_sum = sum(
        delta * zone_weights.get(zone, 0.0)
        for zone, delta in zone_deltas.items()
    )
    total_weight = sum(zone_weights.get(zone, 0.0) for zone in zone_deltas.keys())

    if total_weight == 0:
        return 0.0

    mean_weighted_delta = weighted_delta_sum / total_weight

    # SNR = сигнал / шум. Для H0 (same person) ожидаем delta ≈ 0
    # Чем больше delta — тем ниже SNR (больше сигнал относительно шума)
    if calibration_stats and "sigma_noise" in calibration_stats:
        sigma = calibration_stats["sigma_noise"]
        if sigma > 0:
            # [ITER-1] ИСПРАВЛЕНИЕ: Линейный SNR вместо dB
            snr = compute_linear_snr(mean_weighted_delta, sigma, noise_floor=0.015)
            return snr

    # Fallback: эвристический линейный SNR на основе дивергенции
    # [ITER-1] ИСПРАВЛЕНИЕ: Убрано преобразование в dB
    # Чем меньше delta — тем выше SNR (лучшее совпадение)
    fallback_noise = 0.02  # Базовый шум для fallback
    snr = compute_linear_snr(mean_weighted_delta, fallback_noise, noise_floor=0.015)
    return snr





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
    [FIX Бага #4] Определяет pose bucket из yaw/pitch/roll.
    Исправлено: 5-уровневая система бакетов с правильными диапазонами.
    """
    yaw_raw = float(pose.get("yaw", 0.0))
    yaw = abs(yaw_raw)
    side = "right" if yaw_raw > 0 else "left"
    
    if yaw <= 12:
        return "frontal"
    elif yaw <= 25:
        return f"{side}_threequarter_light"
    elif yaw <= 45:
        return f"{side}_threequarter_mid"
    elif yaw <= 65:
        return f"{side}_threequarter_deep"
    else:
        return f"{side}_profile"


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
    # [BUGFIX] Ключи текстур приведены в соответствие с выходом SkinTextureAnalyzer / extract_photo_bundle
    raw_silicone_a = tex_a.get("texture_silicone_prob")
    raw_silicone_b = tex_b.get("texture_silicone_prob")
    # FFT high-freq ratio не вычисляется анализатором — используем GLCM contrast как proxy
    raw_fft_a = tex_a.get("glcm_contrast")
    raw_fft_b = tex_b.get("glcm_contrast")
    # albedo_uniformity не вычисляется — используем GLCM homogeneity как proxy
    raw_albedo_a = tex_a.get("glcm_homogeneity")
    raw_albedo_b = tex_b.get("glcm_homogeneity")
    raw_spec_a = tex_a.get("texture_specular_gloss")
    raw_spec_b = tex_b.get("texture_specular_gloss")
    raw_lbp_a = tex_a.get("texture_lbp_uniformity")
    raw_lbp_b = tex_b.get("texture_lbp_uniformity")
    
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
    
    # [FIX Бага #7] Анти-доказательство для H0 (естественность кожи).
    # КРИТИЧНО: float(val or 0.0) обнуляло natural_score для не-фронтальных фото
    # (поры не видны на профилях) — все фото на профиле казались синтетикой!
    def _safe_avg_natural(val_a, val_b):
        """None-безопасное среднее: None игнорируется, а не заменяется 0."""
        if val_a is None and val_b is None:
            return None
        if val_a is None:
            return float(val_b)
        if val_b is None:
            return float(val_a)
        return (float(val_a) + float(val_b)) / 2
    
    pore_a = tex_a.get("texture_pore_density")
    pore_b = tex_b.get("texture_pore_density")
    lbp_a = tex_a.get("texture_lbp_complexity")
    lbp_b = tex_b.get("texture_lbp_complexity")
    wrink_f_a = tex_a.get("texture_wrinkle_forehead")
    wrink_n_a = tex_a.get("texture_wrinkle_nasolabial")
    wrink_f_b = tex_b.get("texture_wrinkle_forehead")
    wrink_n_b = tex_b.get("texture_wrinkle_nasolabial")
    wrinkle_a = (float(wrink_f_a) + float(wrink_n_a)) / 2 if wrink_f_a is not None and wrink_n_a is not None else None
    wrinkle_b = (float(wrink_f_b) + float(wrink_n_b)) / 2 if wrink_f_b is not None and wrink_n_b is not None else None
    
    pore_avg = _safe_avg_natural(pore_a, pore_b)
    lbp_avg = _safe_avg_natural(lbp_a, lbp_b)
    wrinkle_avg = _safe_avg_natural(wrinkle_a, wrinkle_b)
    
    natural_markers = {
        "pore_density": pore_avg,
        "lbp_complexity": lbp_avg,
        "wrinkle_detail": wrinkle_avg,
    }
    
    # [FIX Бага #7] Нормализуем NATURAL_SCORE только по ДОСТУПНЫМ метрикам
    # (например, поры не видны на профиле — не штрафуем за это!)
    avail_score = 0.0
    avail_weight = 0.0
    if pore_avg is not None:
        avail_score += min(1.0, pore_avg / 50.0) * 0.4
        avail_weight += 0.4
    if lbp_avg is not None:
        avail_score += min(1.0, lbp_avg / 3.0) * 0.35
        avail_weight += 0.35
    if wrinkle_avg is not None:
        avail_score += min(1.0, wrinkle_avg / 20.0) * 0.25
        avail_weight += 0.25
    
    if avail_weight > 0:
        natural_score = avail_score / avail_weight  # Нормализируем по доступным
    else:
        natural_score = 0.5  # Нейтральный маркер при отсутствии любых данных
    
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
    summary_a: dict,
    summary_b: dict,
    calibration_stats: dict = None,
    *args, **kwargs
) -> dict:
    from backend.core.verdict import BayesianForensicEngine

    status_a = summary_a.get("status", "unknown")
    status_b = summary_b.get("status", "unknown")
    if status_a != "ready" or status_b != "ready":
        return {"verdict": "INSUFFICIENT_DATA"}

    metrics_a = summary_a.get("metrics", {})
    metrics_b = summary_b.get("metrics", {})
    tex_a = summary_a.get("texture_forensics", {})
    tex_b = summary_b.get("texture_forensics", {})
    
    year_a = summary_a.get("year", summary_a.get("parsed_year", 2000))
    year_b = summary_b.get("year", summary_b.get("parsed_year", 2000))
    delta_years = abs(year_a - year_b)
    
    # 1. [FIX Бага #1] Считаем дельты по ВСЕМ взвешенным зонам из ZONE_WEIGHTS (не только 3!)
    bone_delta_sum = 0.0
    total_weight = 0.0
    valid_zones = 0
    zone_deltas = {}  # Для последующего SNR
    
    for zone, weight in ZONE_WEIGHTS.items():
        val_a = metrics_a.get(zone)
        val_b = metrics_b.get(zone)
        if val_a is not None and val_b is not None and not (isinstance(val_a, float) and math.isnan(val_a)) and not (isinstance(val_b, float) and math.isnan(val_b)):
            delta = abs(float(val_a) - float(val_b))
            bone_delta_sum += delta * weight
            total_weight += weight
            valid_zones += 1
            zone_deltas[zone] = delta
            
    avg_bone_delta = bone_delta_sum / max(total_weight, 1e-6) if valid_zones > 0 else 0.0
    
    # 2. Подключаем движок из verdict.py
    engine = BayesianForensicEngine()
    
    # [FIX Бага #3] Базовый шум: берём из калибровки, если есть — иначе хардкод 0.04
    base_sigma = 0.04
    if calibration_stats and "sigma_noise" in calibration_stats:
        base_sigma = max(float(calibration_stats["sigma_noise"]), 0.01)
    
    # Надежность берём минимальную из пары
    reliability = min(metrics_a.get("reliability_weight", 0.5), metrics_b.get("reliability_weight", 0.5))
    
    # 3. Текстурное H1 доказательство — реально вычисляем
    tex_h1_result = _compute_texture_h1_evidence(tex_a, tex_b, year_a, year_b)
    texture_h1_likelihood = float(tex_h1_result.get("likelihood", 1e-6))
    
    # 4. Вызов движка (время расширяет дисперсию, а не меняет приор)
    likelihoods = engine.compute_likelihoods(
        metric_delta=avg_bone_delta, 
        base_sigma=base_sigma, 
        delta_years=delta_years, 
        reliability=reliability,
        texture_h1_likelihood=texture_h1_likelihood,
    )
    
    # 5. Байесовское обновление
    priors = engine.priors
    unnormalized_posteriors = priors * likelihoods
    evidence = sum(unnormalized_posteriors)
    if evidence < 1e-15:
        posteriors = priors.copy()
    else:
        posteriors = unnormalized_posteriors / evidence
    
    dominant = ["H0", "H1", "H2"][np.argmax(posteriors)]
    
    # 6. [BUGFIX] Реальные данные вместо захардкоженных фейковых значений
    # Geometry SNR из реальных метрик (не 10.0)
    geom_snr = compute_linear_snr(avg_bone_delta, 0.04, noise_floor=0.015) if valid_zones > 0 else 0.0
    bone_score = float(1.0 - avg_bone_delta) if valid_zones > 0 else 0.0
    
    # Silicone probability из реальных текстур (не 0.0)
    silicone_prob_a = float(tex_a.get("texture_silicone_prob", 0.0) or 0.0)
    silicone_prob_b = float(tex_b.get("texture_silicone_prob", 0.0) or 0.0)
    synthetic_prob = max(silicone_prob_a, silicone_prob_b)
    
    # Текстурные фичи из реальных данных (не 0.5)
    fft_val = tex_h1_result.get("features", {}).get("fft_anomaly")
    lbp_val = tex_h1_result.get("features", {}).get("lbp_uniformity")
    albedo_val = tex_h1_result.get("features", {}).get("albedo_uniformity")
    specular_val = tex_h1_result.get("features", {}).get("specular_gloss")
    
    # 1. ВЫЗВАТЬ КЛАССИФИКАТОР:
    h1_subtype_data = _classify_h1_subtype(
        texture_features=tex_h1_result.get("features", {}),
        geometric_divergence=avg_bone_delta,
        tex_a=tex_a,
        tex_b=tex_b
    )
    
    # Pose distance из реальных углов
    pose_a = summary_a.get("pose", {})
    pose_b = summary_b.get("pose", {})
    pose_distance = float(np.sqrt(
        (float(pose_a.get("yaw", 0) - pose_b.get("yaw", 0))) ** 2 +
        (float(pose_a.get("pitch", 0) - pose_b.get("pitch", 0))) ** 2 +
        (float(pose_a.get("roll", 0) - pose_b.get("roll", 0))) ** 2
    ))
    
    # Сборка true coverage
    from backend.core.scoring import compute_true_coverage
    bucket_a = summary_a.get("bucket", "unclassified")
    coverage_ratio = compute_true_coverage(metrics_a, bucket_a)
    return {
        "verdict": dominant,
        "delta_years": delta_years,
        "geometric_divergence": avg_bone_delta,
        "priors": {"H0": float(priors[0]), "H1": float(priors[1]), "H2": float(priors[2])},
        "likelihoods": {"H0": float(likelihoods[0]), "H1": float(likelihoods[1]), "H2": float(likelihoods[2])},
        "posteriors": {"H0": float(posteriors[0]), "H1": float(posteriors[1]), "H2": float(posteriors[2])},
        "dataQuality": {
            "coverageRatio": coverage_ratio,
            "missingZonesA": [],
            "missingZonesB": [],
        },
        "geometric": {
            "snr": float(geom_snr),
            "boneScore": bone_score,
            "ligamentScore": 1.0,
            "softTissueScore": 1.0,
            "zoneCount": valid_zones,
            "excludedZones": [],
            "categoryDivergence": {},
        },
        "texture": {
            "syntheticProb": float(synthetic_prob),
            "h1_subtype": h1_subtype_data,
            "rawSyntheticProb": float(tex_h1_result.get("raw_composite", 0.0)),
            "naturalScore": float(tex_h1_result.get("naturalScore", 0.5)),
            "fft": float(fft_val) if fft_val is not None else None,
            "lbp": float(lbp_val) if lbp_val is not None else None,
            "albedo": float(albedo_val) if albedo_val is not None else None,
            "specular": float(specular_val) if specular_val is not None else None,
            "textureFeatures": tex_h1_result.get("features", {}),
            "naturalMarkers": tex_h1_result.get("naturalMarkers", {}),
            "epochAdjustments": tex_h1_result.get("epochAdjustments", {}),
        },
        "chronology": {
            "deltaYears": delta_years,
            "boneJump": avg_bone_delta,
            "ligamentJump": 0.0,
            "flags": [],
        },
        "pose": {
            "mutualVisibility": 1.0,
            "expressionExcluded": 0,
            "poseDistanceDeg": pose_distance,
        },
        "likelihoods_summary": {
            "H0": float(likelihoods[0]),
            "H1": float(likelihoods[1]),
            "H2": float(likelihoods[2]),
        },
        "zone_deltas": zone_deltas,
        "H0": float(posteriors[0]),
        "H1": float(posteriors[1]),
        "H2": float(posteriors[2]),
        "computationLog": [
            f"BayesianForensicEngine calculated new posteriors",
            f"Bone Delta: {avg_bone_delta:.4f}",
            f"Delta Years: {delta_years}",
            f"Texture H1 Likelihood: {texture_h1_likelihood:.4f}",
            f"Geometry SNR: {geom_snr:.4f}",
        ]
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
    # [BUGFIX] pose_confidence не существует в ReconstructionResult
    # Убираем эту проверку — доверие к реконструкции оцениваем по другим критериям
    pose_quality = 0.8  # Дефолт для отсутствующего атрибута
    
    # 3. Проверяем параметры трансформации
    trans_params = getattr(recon, 'trans_params', None)
    if trans_params is None:
        issues.append("Missing transformation parameters")
        transform_quality = 0.0
    else:
        # [BUGFIX] trans_params это ndarray, не dict
        # Проверяем разумность значений трансляции и масштаба
        if isinstance(trans_params, np.ndarray) and trans_params.size >= 3:
            # trans_params: [scale, crop_width, crop_height, cx, cy] в 3DDFA
            # Проверяем масштаб
            scale = float(trans_params[0]) if trans_params.size > 0 else 1.0
            if scale < 0.3 or scale > 3.0:
                issues.append(f"Abnormal scale: {scale:.2f}")
                transform_quality = 0.5
            else:
                transform_quality = 1.0
        else:
            issues.append("Invalid transformation parameters format")
            transform_quality = 0.0
    
    # 4. Проверяем углы (не должны быть экстремальными)
    angles = getattr(recon, 'angles_deg', None)
    if angles is not None:
        # [FIX Бага #8] Порядок углов 3DDFA: [pitch, yaw, roll] — НЕ [yaw, pitch, roll]!
        pitch, yaw, roll = angles if len(angles) >= 3 else (0, 0, 0)
        if abs(yaw) > 60:
            issues.append(f"Extreme yaw: {yaw:.1f}°")
        if abs(pitch) > 45:
            issues.append(f"Extreme pitch: {pitch:.1f}°")
    
    # 5. Комбинированный trust score
    trust_score = (
        vertex_quality * 0.4 +
        pose_quality * 0.3 +
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
            "pose_quality": pose_quality,
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


def _recon_dict(reconstruction: Any, bucket: str | None = None, image_shape: tuple[int, int] | None = None) -> dict[str, Any]:
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

    vertices = reconstruction.vertices_world

    return {
        "triangles": reconstruction.triangles,
        "uv_coords": reconstruction.uv_coords,
        "vertices": vertices,
        "vertices_2d": v2d_orig,
        "vertices_3d": vertices,
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


def _save_uv_assets(image_bgr: np.ndarray, reconstruction: Any, output_dir: Path, bucket: str | None = None) -> dict[str, str]:
    runtime = get_runtime()
    _uv_tex_analysis, uv_tex_beauty, _uv_mask, uv_conf, _aux = runtime.uv.generate(image_bgr, _recon_dict(reconstruction, bucket, image_bgr.shape))
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
        for vertex in vertices:
            handle.write(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}\n")
        if uv_coords is not None:
            for uv in uv_coords:
                handle.write(f"vt {uv[0]:.6f} {1.0 - uv[1]:.6f}\n")
        for normal in normals:
            handle.write(f"vn {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}\n")
        handle.write("g face\n")
        handle.write("usemtl FaceMaterial\n")
        for triangle in triangles:
            a, b, c = (int(index) + 1 for index in triangle.tolist())
            handle.write(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n")

    return {"mesh_obj": obj_path.name, "mesh_mtl": mtl_path.name}


def sanitize_for_json(obj):
    import math
    import numpy as np
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    elif isinstance(obj, bool):
        return obj
    elif isinstance(obj, (float, np.floating, np.float32, np.float64)):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return None
        return round(val, 3)
    elif isinstance(obj, (int, np.integer, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return sanitize_for_json(obj.tolist())
    else:
        return obj


def _safe_atomic_write_json(target_path: Path, data: dict):
    import json, tempfile, os
    from backend.core.utils import _NumpyEncoder
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=str(target_path.parent), suffix=".tmp")
    try:
        clean_data = sanitize_for_json(data)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(clean_data, f, ensure_ascii=False, indent=2, cls=_NumpyEncoder)
        os.replace(temp_path, str(target_path))
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e


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

    reconstruction = resolve_reconstruction(
        runtime.reconstruction,
        source_path,
        output_dir,
        neutral_expression=False,
    )

    # [BUGFIX] Attempt to use the highly accurate HighResHeadPoseEstimator first
    pose_dict = None
    try:
        from backend.core.head_pose import HighResHeadPoseEstimator
        estimator = HighResHeadPoseEstimator()
        hr_pose = estimator.predict(source_path)
        if hr_pose:
            yaw = hr_pose["yaw"]
            pitch = hr_pose["pitch"]
            roll = hr_pose["roll"]
            # [BUGFIX] Invert yaw sign to match the legacy filename logic which expected left = negative, right = positive
            # Note: The external model already outputs left = positive, right = negative (standard mathematical yaw)
            # We must invert it to match the rest of the application's filename conventions.
            yaw = -yaw
            
            from backend.core.utils import classify_pose_bucket
            bucket = classify_pose_bucket(yaw)
            
            pose_dict = {
                "yaw": yaw,
                "pitch": pitch,
                "roll": roll,
                "bucket": bucket,
                "pose_source": "mobilenetv3_large",
                "needs_manual_review": abs(yaw) > 45.0,
            }
    except Exception as e:
        logger.error(f"Failed to use HighResHeadPoseEstimator: {e}")

    if pose_dict:
        pose = pose_dict
        bucket = pose["bucket"]
    elif reconstruction and hasattr(reconstruction, 'angles_deg') and reconstruction.angles_deg is not None:
        angles_deg = reconstruction.angles_deg
        # [BUGFIX] Invert the yaw sign to align 3DDFA's coordinate system with the filename pose convention
        yaw = -float(angles_deg[1])
        pitch = float(angles_deg[0])
        roll = float(angles_deg[2])
        bucket = reconstruction.pose_bucket
        pose = {
            "yaw": yaw,
            "pitch": pitch,
            "roll": roll,
            "bucket": bucket,
            "pose_source": "3DDFA_v3",
            "needs_manual_review": abs(yaw) > 45.0,
        }
    else:
        from backend.core.utils import parse_pose_from_filename
        fn_pose = parse_pose_from_filename(source_path.name)
        if fn_pose:
            yaw = fn_pose["yaw"]
            pitch = fn_pose["pitch"]
            roll = fn_pose["roll"]
            bucket = fn_pose["bucket"]
            pose = {
                "yaw": yaw,
                "pitch": pitch,
                "roll": roll,
                "bucket": bucket,
                "pose_source": "filename",
                "needs_manual_review": False,
            }
        else:
            bucket = "frontal"
            pose = {
                "yaw": 0.0, "pitch": 0.0, "roll": 0.0,
                "bucket": bucket, "pose_source": "fallback",
                "needs_manual_review": True
            }

    angle = RAW_BUCKET_TO_UI.get(bucket, bucket)

    raw_result = reconstruction.payload.get("raw_result", {})
    # [PIPE-FIX] Skip render_face/render_shape/render_mask — not needed for pipeline.
    # Only extract UV texture, mask, confidence, mesh, and face crop (like v2 script).
    uv_artifacts = _save_uv_assets(image_bgr, reconstruction, output_dir, bucket) if runtime.uv else {}
    mesh_artifacts = _save_mesh_assets(reconstruction, uv_artifacts.get("uv_texture", "uv_texture.png"), output_dir) if uv_artifacts else {}

    # Build face crop from seg_visible (like v2 script's apply_segmentation_mask)
    face_crop_name = _save_face_crop(image_bgr, reconstruction, output_dir)

    # Copy original photo to output directory for UI use
    import shutil
    original_copy_name = source_path.name
    # Only copy if source is not already in output_dir (e.g., for uploaded files)
    if source_path.parent != output_dir:
        shutil.copy2(source_path, output_dir / original_copy_name)

    # Texture analysis on face_crop.jpg (like v2 script — masked crop, no separate mask needed)
    face_crop_path = output_dir / face_crop_name if face_crop_name else None
    texture_forensics = runtime.texture.analyze_image(face_crop_path or source_path, None)
    quality = runtime.quality.evaluate(source_path)
    geometry_metrics, pose_reliability = _compute_geometry_metrics(reconstruction, bucket)


    # 1. Рассчитываем вероятность силикона (H1) на лету
    gloss = texture_forensics.get("specular_gloss", 0.0) or 0.0
    uniformity = texture_forensics.get("lbp_uniformity", 0.0) or 0.0
    pore_density = texture_forensics.get("nose_pore_density", 0.0) or 0.0
    
    silicone_prob = runtime.texture.compute_synthetic_probability(
        specular_gloss=gloss,
        lbp_uniformity=uniformity,
        pore_density=pore_density
    )
    texture_forensics["texture_silicone_prob"] = silicone_prob

    # Взвешенная надежность (Weighted Reliability)
    # Геометрия (3D) важнее для криминалистики, чем идеальный фокус текстуры
    tex_reliability = float(texture_forensics.get("quality_index", 0.5) or 0.5)
    if quality.get("overall_score", 0) > 0.8:
        tex_reliability = max(tex_reliability, 0.6)

    # Берем взвешенное среднее: 70% доверяем геометрии (поза), 30% текстура
    final_reliability = (pose_reliability * 0.7) + (tex_reliability * 0.3)

    # 2. ПРАВИЛЬНЫЙ МАППИНГ ТЕКСТУР В МЕТРИКИ (Устранение бага нулей)
    metrics = {
        **geometry_metrics,
        "reliability_weight": float(final_reliability),
        "texture_lbp_complexity": float(texture_forensics.get("lbp_entropy", 0.0) or 0.0),
        "texture_lbp_uniformity": float(uniformity),
        "texture_specular_gloss": float(gloss),
        "texture_silicone_prob": float(silicone_prob),
        "texture_pore_density": float(pore_density),
        "texture_spot_density": float(texture_forensics.get("spot_density", 0.0) or 0.0),
        "texture_wrinkle_forehead": float(texture_forensics.get("wrinkle_forehead", 0.0) or 0.0),
        "texture_wrinkle_nasolabial": float(texture_forensics.get("nasolabial_depth", 0.0) or 0.0),
        "texture_global_smoothness": float(1.0 / (float(texture_forensics.get("laplacian_energy", 0.01) or 0.01) * 1000 + 1.0)),
        "glcm_contrast": float(texture_forensics.get("glcm_contrast", 0.0) or 0.0),
        "glcm_energy": float(texture_forensics.get("glcm_energy", 0.0) or 0.0),
        "glcm_homogeneity": float(texture_forensics.get("glcm_homogeneity", 0.0) or 0.0),
        "glcm_correlation": float(texture_forensics.get("glcm_correlation", 0.0) or 0.0),
    }

    # Безопасно удаляем неиспользуемые null
    texture_forensics.pop("uv_spot_density", None)
    texture_forensics.pop("uv_texture_entropy", None)
    texture_forensics.pop("uv_silicone_flatness", None)
    texture_forensics.pop("uv_wrinkle_energy", None)
    texture_forensics.pop("uv_retouch_score", None)

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
        "reliability_tier": "high" if final_reliability > 0.75 else ("medium" if final_reliability > 0.4 else "low"),
        "usable_for_comparison": bool(final_reliability > 0.35 and quality.get("overall_score", 0) > 0.4),
    }
    
    # [FIX-YR1] Add date/year fields for calculate_bayesian_evidence compatibility
    date_str, parsed_date = parse_date_from_name(source_path.name)
    if not parsed_date:
        date_str, parsed_date = fallback_date_for_file(source_path)
    date_source = "filename" if parsed_date else "fallback"
    from backend.core.scoring import compute_true_coverage

    summary = {
        "photo_id": photo_id,
        "dataset": dataset,
        "filename": source_path.name,
        "source_path": str(source_path),
        "file_size_bytes": source_path.stat().st_size,
        "date_str": date_str,
        "date_source": date_source,
        "year": parsed_date.year if parsed_date else None,
        "parsed_year": parsed_date.year if parsed_date else None,
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
            "face_crop": face_crop_name,
            "original_photo": original_copy_name,
        },
        "status": "ready" if status_detail["usable_for_comparison"] else "needs_review",
        "status_detail": status_detail,  # [FIX-84] Развернутый статус
        "dataQuality": {"coverageRatio": compute_true_coverage(metrics, bucket)},
        "lineage": lineage,  # [FIX-87, FIX-96] Полная trace-цепочка
        "extracted_at": iso_now(),
        "artifact_version": ARTIFACT_VERSION,
        "methodology_version": METHODOLOGY_VERSION,  # [FIX-95] Версия методики
        "runtime_config_hash": ForensicManifest.compute_manifest_id(photo_id, runtime),
    }
    _safe_atomic_write_json(output_dir / "summary.json", summary)
    _safe_atomic_write_json(output_dir / f"{photo_id}_summary.json", summary)
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
        "texture_lbp_complexity": float(texture_forensics.get("lbp_entropy", 0.0)),
        "texture_lbp_uniformity": float(texture_forensics.get("lbp_uniformity", 0.0)),
        "texture_specular_gloss": float(texture_forensics.get("specular_gloss", 0.0)),
        "texture_silicone_prob": float(texture_forensics.get("texture_silicone_prob", 0.0)),
        "texture_pore_density": float(texture_forensics.get("nose_pore_density", 0.0)),
        "texture_wrinkle_forehead": float(texture_forensics.get("wrinkle_forehead", 0.0)),
        "texture_wrinkle_nasolabial": float(texture_forensics.get("nasolabial_depth", 0.0)),
        "texture_global_smoothness": float(1.0 / (float(texture_forensics.get("laplacian_energy", 0.01) or 0.01) * 1000 + 1.0)),
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
