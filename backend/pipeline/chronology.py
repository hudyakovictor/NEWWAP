from __future__ import annotations

import re
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass

from core.constants import (
    REFERENCE_PERIOD_END, RTR_RATIO, RTR_MIN_ABS_DELTA, IMPOSSIBLE_AGE_REVERSAL_DAYS,
    CHRONO_FLAG_IMPOSSIBLE, CHRONO_FLAG_RETURN, CHRONO_FLAG_TRANSITION
)
from core.utils import iso_now, BUCKET_METRIC_KEYS


def get_ordered_metric_vector(metrics_dict: dict, required_keys: list) -> np.ndarray:
    """
    [ITER-1] Гарантированный порядок ключей перед вычислением L2 нормы.
    [BUGFIX] Missing metrics = NaN вместо 0.0. Раньше 0.0 создавал ложную
    стабильность: два фото с разными missing metrics выглядели одинаково,
    потому что оба имели 0.0 для отсутствующих ключей.
    """
    vector = []
    for key in sorted(required_keys):
        val = metrics_dict.get(key)
        if val is None:
            vector.append(np.nan)
        elif isinstance(val, float) and np.isnan(val):
            vector.append(np.nan)
        else:
            vector.append(float(val))
    return np.array(vector, dtype=np.float64)


def get_ordered_metric_vectors(metrics_a: dict, metrics_b: dict, required_keys: list) -> Tuple[np.ndarray, np.ndarray]:
    """
    [CH-02] Вычисляет векторы метрик только по общим ключам, чтобы избежать искажений расстояния.
    """
    common = set(metrics_a.keys()) & set(metrics_b.keys()) & set(required_keys)
    sorted_keys = sorted(list(common))
    v1 = np.array([metrics_a[k] for k in sorted_keys], dtype=np.float64)
    v2 = np.array([metrics_b[k] for k in sorted_keys], dtype=np.float64)
    return v1, v2


class SuspiciousWindow:
    """
    [CHRONO-04] Temporal Window Analysis.
    Tracks prior probability of substitution within a specific timeframe.
    """
    def __init__(self, start_date: datetime, end_date: datetime):
        self.start_date = start_date
        self.end_date = end_date
        self.days = (end_date - start_date).days
        self.prior_p_substitution = 0.0
        self._calculate_p_substitution()

    def _calculate_p_substitution(self):
        # [ITER-3] Prior probability increases as time gap decreases for large deviations
        if self.days < IMPOSSIBLE_AGE_REVERSAL_DAYS:
            self.prior_p_substitution = 0.8
        elif self.days < 90:
            self.prior_p_substitution = 0.4
        else:
            self.prior_p_substitution = 0.1

def parse_forensic_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str: return None
    try:
        return datetime.fromisoformat(date_str.split('T')[0].split('.')[0])
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y_%m_%d", "%Y"):
            try:
                return datetime.strptime(date_str[:len(fmt)], fmt)
            except ValueError:
                continue
    return None

def is_reference_period(date: datetime | str | None) -> bool:
    if date is None: return False
    dt = parse_forensic_date(date) if isinstance(date, str) else date
    if not dt: return False
    ref_end = datetime.fromisoformat(REFERENCE_PERIOD_END)
    return dt <= ref_end

class ChronologyAnalyzer:
    """
    [ITER-3] Chronology Engine (Gate-0).
    Detects temporal anomalies, impossible transitions, and identity swaps.
    """
    def __init__(self, deviation_threshold: float = 1.2):
        self.deviation_threshold = deviation_threshold

    def check_pair_consistency(self, date_a: str, date_b: str, y_a: float = 0.0, y_b: float = 0.0) -> List[Dict[str, Any]]:
        """
        [GATE-0] Fast temporal check for a pair of images.
        """
        flags = []
        d1 = parse_forensic_date(date_a)
        d2 = parse_forensic_date(date_b)
        
        if not d1 or not d2:
            return flags
            
        # Ensure chronological order for comparison logic
        if d1 > d2:
            d1, d2 = d2, d1
            y_a, y_b = y_b, y_a
        
        days_delta = abs((d2 - d1).days)
        window = SuspiciousWindow(d1, d2)
        
        # Check for age reversal: younger_score(b) > younger_score(a) when date_b > date_a
        is_reversal = y_b > y_a
        
        if days_delta < IMPOSSIBLE_AGE_REVERSAL_DAYS and is_reversal:
            flags.append({
                "type": CHRONO_FLAG_IMPOSSIBLE,
                "severity": "critical",
                "prior_p": window.prior_p_substitution,
                "description": f"Extremely short timeframe ({days_delta} days) with biometric age reversal."
            })
            
        return flags

    def analyze_timeline(self, photos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enriches photos with temporal metadata and anomaly flags.
        """
        if not photos: return []

        buckets = defaultdict(list)
        for p in photos:
            bucket = p.get("bucket", "unknown")
            buckets[bucket].append(p)

        for bucket, bucket_photos in buckets.items():
            # [BUGFIX] Sort by actual photo date (date_str) not extraction time (extracted_at)
            bucket_photos.sort(key=lambda x: x.get("date_str", ""))
            
            for i in range(len(bucket_photos)):
                curr = bucket_photos[i]
                flags = curr.setdefault("anomaly_flags", [])
                
                if i == 0: continue
                
                prev = bucket_photos[i-1]
                d1 = parse_forensic_date(prev.get("date_str"))
                d2 = parse_forensic_date(curr.get("date_str"))
                
                if not d1 or not d2: continue
                
                days_delta = (d2 - d1).days
                window = SuspiciousWindow(d1, d2)
                
                if days_delta > 365:
                    flags.append({
                        "type": "long_gap",
                        "severity": "medium",
                        "description": f"Gap of {days_delta} days detected (White Zone)."
                    })
                
                # Deviation Analysis
                # [ITER-1] ИСПРАВЛЕНИЕ: Используем упорядоченные векторы метрик
                metrics_keys = sorted(set(prev.get("metrics", {}).keys()) | set(curr.get("metrics", {}).keys()))
                m1, m2 = get_ordered_metric_vectors(prev.get("metrics", {}), curr.get("metrics", {}), metrics_keys)

                if m1.size > 0 and m1.size == m2.size:
                    dist = float(np.linalg.norm(m1 - m2))
                    if dist > self.deviation_threshold:
                        if window.prior_p_substitution > 0.5:
                            flags.append({
                                "type": CHRONO_FLAG_IMPOSSIBLE,
                                "severity": "critical",
                                "description": f"Critical geometric change (dist={dist:.3f}) in <{IMPOSSIBLE_AGE_REVERSAL_DAYS} days."
                            })
                        else:
                            flags.append({
                                "type": CHRONO_FLAG_TRANSITION,
                                "severity": "medium",
                                "description": f"Significant deviation (dist={dist:.3f}) over {days_delta} days."
                            })


                # [ITER-3.1] Forensic-specific checks within same bucket
                metrics_curr = curr.get("metrics", {})
                metrics_prev = prev.get("metrics", {})
                
                # 1. Инверсия асимметрии (Asymmetry Inversion)
                if 'asymmetry_total_vector' in metrics_curr and 'asymmetry_total_vector' in metrics_prev:
                    v1 = metrics_prev['asymmetry_total_vector']
                    v2 = metrics_curr['asymmetry_total_vector']
                    # Если перекос изменил знак или резко вырос при малом окне
                    if abs(v2 - v1) > 0.5 and window.days < 180:
                        flags.append({
                            "type": "asymmetry_inversion",
                            "severity": "critical",
                            "description": "Detected impossible bone structure inversion (Asymmetry flip)."
                        })

                # 2. Скачок связочного аппарата (Rapid Ligament Movement)
                lig_keys = [k for k in metrics_curr if 'ligament' in k]
                for k in lig_keys:
                    if k in metrics_prev:
                        if abs(metrics_curr[k] - metrics_prev[k]) > 0.3:
                            flags.append({
                                "type": "ligament_drift",
                                "severity": "high",
                                "description": f"Abnormal ligament movement detected ({k})."
                            })


                # [ITER-3] RTR Detector (Return To Reference)
                # [BUGFIX] Use actual photo date (date_str) not extraction time (extracted_at)
                if not is_reference_period(curr.get("date_str")):
                    ref_photos = [p for p in bucket_photos[:i] if is_reference_period(p.get("date_str"))]
                    if ref_photos:
                        # [ITER-1] ИСПРАВЛЕНИЕ: Используем упорядоченные векторы метрик по общим ключам
                        all_ref_keys = sorted(set().union(*[p.get("metrics", {}).keys() for p in ref_photos]))
                        common_r_keys = set(curr.get("metrics", {}).keys()) & set(all_ref_keys)
                        valid_ref_photos = [p for p in ref_photos if all(k in p.get("metrics", {}) for k in common_r_keys)]
                        if valid_ref_photos:
                            ref_metrics = []
                            for p in valid_ref_photos:
                                r_vec, _ = get_ordered_metric_vectors(p.get("metrics", {}), p.get("metrics", {}), sorted(list(common_r_keys)))
                                ref_metrics.append(r_vec)
                            ref_avg = np.mean(ref_metrics, axis=0)
                            curr_vec, _ = get_ordered_metric_vectors(curr.get("metrics", {}), curr.get("metrics", {}), sorted(list(common_r_keys)))
                            dist_to_ref = float(np.linalg.norm(curr_vec - ref_avg))
                            dist_to_prev = float(np.linalg.norm(curr_vec - m1)) if m1.size > 0 else 999.0

                            if dist_to_ref < dist_to_prev * RTR_RATIO and dist_to_prev > RTR_MIN_ABS_DELTA:
                                flags.append({
                                    "type": CHRONO_FLAG_RETURN,
                                    "severity": "critical",
                                    "description": "Return to 1999-2001 baseline detected (Deepfake/Mask indicator)."
                                })

        return photos


@dataclass
class TimelineReport:
    flags: List[Dict[str, Any]]


def analyze_timeline_calibrated(
    timeline_photos: List[Dict[str, Any]], 
    pair_engine: Any, 
    reference_date: str = "2001-12-31"
) -> TimelineReport:
    """
    Проходит по временной шкале и оценивает откалиброванные SNR-скачки.
    """
    # Сортировка строго по datetime, а не строкам (Фикс бага CH-02)
    photos = sorted(timeline_photos, key=lambda x: datetime.fromisoformat(x['date'].split('T')[0]))
    
    baseline_photos = [p for p in photos if p['date'] <= reference_date]
    if not baseline_photos:
        baseline_photos = [photos[0]]
    primary_baseline = baseline_photos[0] # Можно заменить на медиану
    
    flags = []
    
    for i in range(1, len(photos)):
        prev_photo = photos[i-1]
        curr_photo = photos[i]
        
        # 1. Сравниваем с предыдущим годом (T_i vs T_{i-1})
        res_to_prev = pair_engine.compare(prev_photo, curr_photo)
        
        # 2. Сравниваем с эталоном молодости (T_i vs 1999)
        res_to_baseline = pair_engine.compare(primary_baseline, curr_photo)
        
        # 3. Логика Impossible Transition (Резкая подмена)
        # Если SNR > 3.0 (сигнал превышает шум в 3 раза), и это не объясняется мимикой
        if res_to_prev.snr > 3.0:
            flags.append({
                "type": "IMPOSSIBLE_TRANSITION",
                "date": curr_photo['date'],
                "snr": res_to_prev.snr,
                "anomalous_zones": [
                    z.get("zone", "") for z in res_to_prev.zone_details if z.get("snr", 0.0) > 3.0
                ] if hasattr(res_to_prev, "zone_details") else []
            })
            
        # 4. Логика Return To Reference (RTR)
        # Если человек резко изменился по сравнению с прошлым годом (SNR_prev > 2.5), 
        # НО при этом его лицо идеально совпадает с лицом 1999 года (SNR_baseline < 1.0)
        if res_to_prev.snr > 2.5 and res_to_baseline.snr < 1.5:
             flags.append({
                "type": "RETURN_TO_REFERENCE",
                "date": curr_photo['date'],
                "evidence": f"Matched baseline {primary_baseline['date']} despite breaking continuity from {prev_photo['date']}"
            })

    return TimelineReport(flags=flags)

