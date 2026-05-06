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

def _compute_linear_snr(signal_error: float, noise_baseline: float) -> float:
    """
    [ITER-1] Вычисляет строго линейный SNR без перехода в децибелы.
    """
    # Запрещаем отрицательный шум и ставим жесткий нижний предел (floor),
    # чтобы избежать взрывного роста SNR при идеальных масках (G-03).
    safe_noise = max(abs(noise_baseline), 0.005)

    # Сигнал не может быть отрицательным
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
            
            # Bayesian-like reliability: 1 / (1 + noise_variance)
            reliability = 1.0 / (1.0 + mean * 100.0 + std * 50.0)
            
            self.zone_profiles[zone] = ZoneNoiseProfile(
                zone_name=zone,
                mean=mean,
                std=std,
                count=len(errors),
                reliability=float(np.clip(reliability, 0.1, 1.0))
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

            # [ITER-1] ИСПРАВЛЕНИЕ: Используем унифицированную функцию линейного SNR
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
    pool = calib_df[calib_df["bucket"] == bucket].copy()
    if len(pool) < k:
        pool = calib_df.copy()  # fallback — весь датасет

    pool["_dist"] = np.sqrt(
        3.0 * (pool["pose_yaw"]   - target_yaw)   ** 2 +
        3.0 * (pool["pose_pitch"] - target_pitch) ** 2 +
        1.5 * (pool["quality_overall"] - target_quality) ** 2 +
        0.5 * (pool["expression_mouth_open_intensity"] - target_expr_mouth) ** 2 +
        0.5 * (pool["expression_smile_intensity"]      - target_expr_smile) ** 2
    )
    return pool.nsmallest(k, "_dist").drop(columns=["_dist"])


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
    from .alignment import canonicalize_vertices_for_bucket
    from .visibility import compute_visibility_from_normals

    rows = []
    by_bucket = calib_df.groupby("bucket")

    for bucket, group in by_bucket:
        photos = group.to_dict("records")
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
                row = {
                    "bucket": bucket,
                    "photo_a": pa["filename"],
                    "photo_b": pb["filename"],
                    "yaw_a": pa["pose_yaw"],
                    "yaw_b": pb["pose_yaw"],
                    "pitch_a": pa["pose_pitch"],
                    "pitch_b": pb["pose_pitch"],
                    "quality_a": pa["quality_overall"],
                    "quality_b": pb["quality_overall"],
                    "expr_mouth_a": pa["expression_mouth_open_intensity"],
                    "expr_smile_a": pa["expression_smile_intensity"],
                    **zone_errors,
                }
                rows.append(row)
            except Exception:
                continue

    pd.DataFrame(rows).to_csv(output_path, index=False)

