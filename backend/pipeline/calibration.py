from __future__ import annotations

import json
import numpy as np
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from .types import AlignmentResult, VisibilityResult
from core.utils import iso_now, read_json, write_json


from typing import Any, Dict, List, Optional, Protocol
import re


def parse_angles_from_filename(filename: str) -> Dict[str, float]:
    """
    [BUGFIX-7] Парсит истинные углы из filename калибровочного датасета.
    Поддерживает форматы:
    - yaw_+30_pitch_-10_roll_+05
    - y30_p-10_r5
    - yaw+30_pitch-10_roll+05
    
    :param filename: Имя файла (например, "person_001_yaw_+30_pitch_-10_roll_+05.jpg")
    :return: Словарь с углами {"yaw": float, "pitch": float, "roll": float}
    """
    angles = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
    
    # Паттерн 1: yaw_+30_pitch_-10_roll_+05
    pattern1 = r"(?:yaw|y)[_]?([+-]?\d+)"
    match1 = re.search(pattern1, filename, re.IGNORECASE)
    if match1:
        angles["yaw"] = float(match1.group(1))
    
    pattern2 = r"(?:pitch|p)[_]?([+-]?\d+)"
    match2 = re.search(pattern2, filename, re.IGNORECASE)
    if match2:
        angles["pitch"] = float(match2.group(1))
    
    pattern3 = r"(?:roll|r)[_]?([+-]?\d+)"
    match3 = re.search(pattern3, filename, re.IGNORECASE)
    if match3:
        angles["roll"] = float(match3.group(1))
    
    return angles

def _compute_linear_snr(signal_error: float, noise_baseline: float) -> float:
    """
    [CRITICAL FIX] Вычисляет линейный SNR — совместимый с порогами в pipeline/verdict.py.

    БЫЛО: _compute_snr_db() — возвращал децибелы (-30...+30 dB).
    СТАЛО: линейный SNR (0.0...∞), совместимый с:
      - SNR_UNCERTAIN_THRESHOLD = 1.0  (из core/constants.py)
      - SNR_SIGNAL_THRESHOLD    = 2.0  (из core/constants.py)
      - pipeline/verdict.py BayesianMultiHypothesisEngine.synthesize()

    При dB-шкале threshold=2.0 означал ~1.58× (почти нет сигнала),
    что делало CalibrationAnalyzer.is_significant полностью бессмысленным.
    """
    # Жёсткий нижний предел шума для защиты от взрывного роста (G-03)
    safe_noise = max(abs(noise_baseline), 0.005)

    # Сигнал = превышение над ожидаемым шумом (не может быть отрицательным)
    safe_signal = max(signal_error - safe_noise, 0.0)

    return safe_signal / safe_noise

@dataclass
class CalibrationDecomposition:
    signal: float
    noise: float
    snr: float

class CalibrationProtocol(Protocol):
    def decompose(self, raw_error: float, pose_delta: float) -> CalibrationDecomposition:
        ...


@dataclass
class NoiseObservation:
    """A single noise observation from a same-person comparison."""
    photo_id_a: str
    photo_id_b: str
    pose_delta_mag: float
    zone_errors: Dict[str, float]
    texture_errors: Dict[str, float]
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = iso_now()

@dataclass
class NuisanceDeltas:
    """[FIX C2-01] Факторы нюисанса для динамического расчёта ожидаемого шума."""
    pose_delta_mag: float = 0.0       # Суммарный угловой дельта между ракурсами (градусы)
    quality_degradation: float = 0.0  # Деградация качества [0..1], 0 = идеально

@dataclass
class ZoneNoiseProfile:
    zone_name: str
    mean: float
    std: float
    count: int
    reliability: float
    pose_weight: float = 0.02     # Влияние позы на шум данной зоны
    quality_weight: float = 0.01  # Влияние качества на шум данной зоны

    @property
    def base_mad(self) -> float:
        return self.mean

    def predict_noise(self, pose_delta_mag: float) -> float:
        return self.base_mad + pose_delta_mag * self.pose_weight

class NoiseModel:
    """
    [ITER-2] Bayesian-inspired Noise Model.
    Predicts expected system noise for given pose/quality conditions.
    """
    def __init__(self):
        self.observations: List[NoiseObservation] = []
        self.zone_profiles: Dict[str, ZoneNoiseProfile] = {}
        self.global_reliability: float = 1.0

    def add_observation(self, obs: NoiseObservation):
        self.observations.append(obs)
        self._rebuild()

    def _rebuild(self):
        if not self.observations:
            return
        
        all_zones = set()
        for obs in self.observations:
            all_zones.update(obs.zone_errors.keys())
            
        for zone in all_zones:
            errors = [obs.zone_errors[zone] for obs in self.observations if zone in obs.zone_errors]
            if not errors: continue
            
            mean = float(np.mean(errors))
            std = float(np.std(errors)) if len(errors) > 1 else mean * 0.5
            
            # [BUGFIX-10] Стабилизация функции надежности с использованием сигмоиды
            # Сигмоида обеспечивает плавное насыщение и лучшую устойчивость при малых значениях
            # Формула: reliability = 1 / (1 + exp(k * (noise - threshold)))
            # где noise = mean * 100 + std * 50, k = коэффициент крутизны, threshold = порог
            noise_score = mean * 100.0 + std * 50.0
            # Сигмоида с центром в 1.0 и крутизной 2.0 для плавного перехода
            reliability = 1.0 / (1.0 + np.exp(2.0 * (noise_score - 1.0)))
            
            self.zone_profiles[zone] = ZoneNoiseProfile(
                zone_name=zone,
                mean=mean,
                std=std,
                count=len(errors),
                reliability=float(np.clip(reliability, 0.05, 0.99))  # [BUGFIX-10] Расширен диапазон для большей чувствительности
            )

    def predict_noise(self, zone_name: str, pose_delta_mag: float) -> float:
        profile = self.zone_profiles.get(zone_name)
        if profile:
            return profile.predict_noise(pose_delta_mag)
        return 0.015 * (1.0 + 0.05 * pose_delta_mag) # Fallback prior

    def get_reliability(self, zone_name: str) -> float:
        profile = self.zone_profiles.get(zone_name)
        return profile.reliability if profile else 0.5

@dataclass
class CalibratedComparisonResult:
    """
    [ITER-2] High-precision comparison result with SNR decomposition.
    """
    photo_a: str
    photo_b: str
    pose_delta_mag: float
    
    # SNR = (Measured Error - Predicted Noise) / Predicted Noise
    snr: float
    is_significant: bool
    
    zone_details: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class CalibrationAnalyzer:
    """
    Orchestrates the calibration process and noise model application.
    """
    def __init__(self, model_path: Optional[Path] = None):
        from core.constants import MIN_SUCCESSFUL_PAIRS_FOR_CALIBRATION
        self.min_successful_pairs = MIN_SUCCESSFUL_PAIRS_FOR_CALIBRATION
        self.model_path = model_path
        self.model = NoiseModel()
        if model_path and model_path.exists():
            self.load_model(model_path)

    def load_model(self, path: Path):
        data = read_json(path)
        if data and "observations" in data:
            for obs_data in data["observations"]:
                self.model.add_observation(NoiseObservation(**obs_data))

    def save_model(self, path: Path):
        data = {
            "version": "2.0.0",
            "updated_at": iso_now(),
            "observations": [asdict(obs) for obs in self.model.observations]
        }
        write_json(path, data)

    def analyze_pair(self, measured_errors: Dict[str, float], pose_delta_mag: float) -> CalibratedComparisonResult:
        """
        Decomposes measured errors into noise and signal components.
        """
        zone_details = []
        weighted_snr_sum = 0.0
        weight_sum = 0.0
        
        for zone, error in measured_errors.items():
            pred_noise = self.model.predict_noise(zone, pose_delta_mag)
            reliability = self.model.get_reliability(zone)

            # [FIX SNR] Линейный SNR — совместим с SNR_SIGNAL_THRESHOLD=2.0 в pipeline/verdict.py
            snr = _compute_linear_snr(error, pred_noise)
            signal = max(0.0, error - pred_noise)
            
            zone_details.append({
                "zone": zone,
                "measured": error,
                "predicted_noise": pred_noise,
                "signal": signal,
                "snr": snr,
                "reliability": reliability
            })
            
            weighted_snr_sum += snr * reliability
            weight_sum += reliability
            
        final_snr = weighted_snr_sum / (weight_sum + 1e-6)
        
        return CalibratedComparisonResult(
            photo_a="", # Should be populated by caller
            photo_b="",
            pose_delta_mag=pose_delta_mag,
            snr=final_snr,
            is_significant=bool(final_snr > 2.0), # Standard forensic threshold
            zone_details=zone_details
        )

    def decompose(
        self,
        raw_error: float,
        pose_delta: float,
        zone: Optional[str] = None,
        nuisance: Optional["NuisanceDeltas"] = None,
    ) -> CalibrationDecomposition:
        """
        [FIX C2-01] Декомпозиция с учётом конкретной зоны и нюисанс-факторов.
        Заменяет глобальное avg_base_noise на per-zone динамический шум.
        """
        if nuisance is None:
            nuisance = NuisanceDeltas(pose_delta_mag=pose_delta)

        if zone and zone in self.model.zone_profiles:
            profile = self.model.zone_profiles[zone]
            expected_noise = (
                profile.base_mad
                + nuisance.pose_delta_mag * profile.pose_weight
                + nuisance.quality_degradation * profile.quality_weight
            )
        elif self.model.zone_profiles:
            # Fallback: медиана стабильных зон (не глобальное среднее!)
            stable_priority = ["orbit_L", "orbit_R", "nose_bridge_tip", "forehead"]
            candidates = [
                self.model.zone_profiles[z].base_mad
                for z in stable_priority
                if z in self.model.zone_profiles
            ]
            if not candidates:
                candidates = [p.base_mad for p in self.model.zone_profiles.values()]
            base = float(np.median(candidates))
            expected_noise = base + nuisance.pose_delta_mag * 0.02 + nuisance.quality_degradation * 0.01
        else:
            expected_noise = 0.015 + nuisance.pose_delta_mag * 0.001

        signal = max(raw_error - expected_noise, 0.0)
        snr = _compute_linear_snr(raw_error, expected_noise)

        return CalibrationDecomposition(
            signal=float(signal),
            noise=float(expected_noise),
            snr=float(snr),
        )

    def decompose_with_local_noise(
        self,
        zone_errors: Dict[str, float],
        pose_delta: float,
        local_noise: Dict[str, float],
    ) -> CalibratedComparisonResult:
        """
        Декомпозиция с локальным noise model из nearest-K калибровочных пар.
        local_noise[zone] = медианная ошибка по этой зоне у ближайших калибровочных фото.
        """
        zone_details = []
        weighted_snr_sum = 0.0
        weight_sum = 0.0

        for zone, error in zone_errors.items():
            # Приоритет: local_noise → zone_profiles → prior
            if zone in local_noise and local_noise[zone] > 1e-8:
                pred_noise = local_noise[zone]
                source = "local_calib"
            elif zone in self.model.zone_profiles:
                pred_noise = self.model.zone_profiles[zone].base_mad
                source = "global_calib"
            else:
                pred_noise = 0.015 + pose_delta * 0.001
                source = "prior"

            reliability = self.model.get_reliability(zone)
            snr = _compute_linear_snr(error, pred_noise)
            signal = max(0.0, error - pred_noise)

            zone_details.append({
                "zone": zone, "measured": error,
                "predicted_noise": pred_noise,
                "noise_source": source,
                "signal": signal, "snr": snr,
                "reliability": reliability,
            })
            weighted_snr_sum += snr * reliability
            weight_sum += reliability

        final_snr = weighted_snr_sum / (weight_sum + 1e-6)

        return CalibratedComparisonResult(
            photo_a="", photo_b="",
            pose_delta_mag=pose_delta,
            snr=final_snr,
            is_significant=bool(final_snr > 2.0),
            zone_details=zone_details,
        )




import pandas as pd

def find_calibration_match(
    calib_df: pd.DataFrame,
    target_yaw: float,
    target_pitch: float,
    target_quality: float,
    target_expr_mouth: float,
    target_expr_smile: float,
    bucket: str,
    k: int = 5,
) -> pd.DataFrame:
    """
    Находит K калибровочных фото наиболее близких по условиям съёмки.
    Веса: поза (3x) > качество (1.5x) > мимика (0.5x).
    """
    # [BUGFIX-16] Устранено глубокое копирование DataFrame
    # Используем view вместо копии для экономии памяти
    pool = calib_df[calib_df["bucket"] == bucket]
    if len(pool) < k:
        pool = calib_df  # fallback — весь датасет (view, не копия)

    # [BUGFIX-16] Вычисляем расстояние без добавления колонки в DataFrame
    distances = np.sqrt(
        3.0 * (pool["pose_yaw"].values - target_yaw) ** 2 +
        3.0 * (pool["pose_pitch"].values - target_pitch) ** 2 +
        1.5 * (pool["quality_overall"].values - target_quality) ** 2 +
        0.5 * (pool.get("mouth_open_intensity", pd.Series(0.0, index=pool.index)).values - target_expr_mouth) ** 2 +
        0.5 * (pool.get("smile_intensity", pd.Series(0.0, index=pool.index)).values - target_expr_smile) ** 2
    )
    
    # Сортируем по расстоянию и берем K ближайших
    nearest_indices = np.argsort(distances)[:k]
    result = pool.iloc[nearest_indices].copy()  # Копируем только результат
    return result


def build_calibration_pairs_csv(
    calib_df: pd.DataFrame,
    storage_root: Path,
    output_path: Path,
) -> None:
    """
    Для каждого бакета считает all-pairs ошибки по зонам.
    Результат: calibration_pairs.csv — основа для nearest-matching noise model.
    """
    from itertools import combinations
    from .zones import MACRO_BONE_INDICES
    # [BUGFIX] Removed unused import compute_visibility_from_normals (function does not exist)
    
    # [BUGFIX-14] Ограничение на размер группы для предотвращения OOM
    # Если в бакете слишком много фото, сэмплируем подмножество
    MAX_PHOTOS_PER_BUCKET = 100  # Максимальное количество фото для all-pairs
    
    rows = []
    by_bucket = calib_df.groupby("bucket")

    for bucket, group in by_bucket:
        photos = group.to_dict("records")
        
        # [BUGFIX-14] Сэмплируем если слишком много фото
        if len(photos) > MAX_PHOTOS_PER_BUCKET:
            import random
            photos = random.sample(photos, MAX_PHOTOS_PER_BUCKET)
        
        for pa, pb in combinations(photos, 2):
            try:
                va = np.load(Path(pa["mesh_path"]) / "vertices.npy")
                vb = np.load(Path(pb["mesh_path"]) / "vertices.npy")
                # vertices.npy уже канонические (после правки #2)
                # Считаем per-zone L2 ошибку
                zone_errors = {}
                for zone, idx_set in MACRO_BONE_INDICES.items():
                    idx = np.array(list(idx_set))
                    if idx.size == 0:
                        continue
                    diff = va[idx] - vb[idx]
                    zone_errors[f"zone_{zone}_error"] = float(
                        np.mean(np.linalg.norm(diff, axis=1))
                    )
                # [BUGFIX-7] Парсим истинные углы из filename для верификации
                true_angles_a = parse_angles_from_filename(pa["filename"])
                true_angles_b = parse_angles_from_filename(pb["filename"])
                
                row = {
                    "bucket": bucket,
                    "photo_a": pa["filename"],
                    "photo_b": pb["filename"],
                    "yaw_a": pa["pose_yaw"],
                    "yaw_b": pb["pose_yaw"],
                    "pitch_a": pa["pose_pitch"],
                    "pitch_b": pb["pose_pitch"],
                    # [BUGFIX-7] Истинные углы из filename
                    "true_yaw_a": true_angles_a["yaw"],
                    "true_yaw_b": true_angles_b["yaw"],
                    "true_pitch_a": true_angles_a["pitch"],
                    "true_pitch_b": true_angles_b["pitch"],
                    "true_roll_a": true_angles_a["roll"],
                    "true_roll_b": true_angles_b["roll"],
                    "quality_a": pa["quality_overall"],
                    "quality_b": pb["quality_overall"],
                    "expr_mouth_a": pa.get("mouth_open_intensity", 0.0),
                    "expr_smile_a": pa.get("smile_intensity", 0.0),
                    **zone_errors,
                }
                rows.append(row)
            except Exception:
                continue

    pd.DataFrame(rows).to_csv(output_path, index=False)

