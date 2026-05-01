from __future__ import annotations

import json
import numpy as np
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from .types import AlignmentResult, VisibilityResult
from core.utils import iso_now, read_json, write_json


def _compute_linear_snr(signal_error: float, noise_baseline: float) -> float:
    """
    [ITER-1] Вычисляет строго линейный SNR без перехода в децибелы.
    """
    # Запрещаем отрицательный шум и ставим жесткий нижний предел (floor),
    # чтобы избежать взрывного роста SNR при идеальных масках.
    safe_noise = max(abs(noise_baseline), 0.015)

    # Сигнал не может быть отрицательным
    safe_signal = max(signal_error - safe_noise, 0.0)

    return safe_signal / safe_noise

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
class ZoneNoiseProfile:
    zone_name: str
    mean: float
    std: float
    count: int
    reliability: float
    
    def predict_noise(self, pose_delta_mag: float) -> float:
        # Simple linear model for now: base_noise + slope * delta
        # In a real scenario, this would be more complex
        return self.mean * (1.0 + 0.02 * pose_delta_mag)

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
