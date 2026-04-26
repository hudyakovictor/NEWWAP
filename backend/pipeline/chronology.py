from __future__ import annotations

import re
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

from core.constants import REFERENCE_PERIOD_END, RTR_RATIO, RTR_MIN_ABS_DELTA, IMPOSSIBLE_SHORTENING_DAYS
from .utils import iso_now

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
        if self.days < IMPOSSIBLE_SHORTENING_DAYS:
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

    def check_pair_consistency(self, date_a: str, date_b: str) -> List[Dict[str, Any]]:
        """
        [GATE-0] Fast temporal check for a pair of images.
        """
        flags = []
        d1 = parse_forensic_date(date_a)
        d2 = parse_forensic_date(date_b)
        
        if not d1 or not d2:
            return flags
            
        # Ensure chronological order for comparison logic
        if d1 > d2: d1, d2 = d2, d1
        
        days_delta = abs((d2 - d1).days)
        window = SuspiciousWindow(d1, d2)
        
        if days_delta < IMPOSSIBLE_SHORTENING_DAYS:
            flags.append({
                "type": "impossible_short",
                "severity": "critical",
                "prior_p": window.prior_p_substitution,
                "description": f"Extremely short timeframe ({days_delta} days) for biometric changes."
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
            bucket_photos.sort(key=lambda x: x.get("extracted_at", ""))
            
            for i in range(len(bucket_photos)):
                curr = bucket_photos[i]
                flags = curr.setdefault("anomaly_flags", [])
                
                if i == 0: continue
                
                prev = bucket_photos[i-1]
                d1 = parse_forensic_date(prev.get("extracted_at"))
                d2 = parse_forensic_date(curr.get("extracted_at"))
                
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
                m1 = np.array(list(prev.get("metrics", {}).values()))
                m2 = np.array(list(curr.get("metrics", {}).values()))
                
                if m1.size > 0 and m1.size == m2.size:
                    dist = float(np.linalg.norm(m1 - m2))
                    if dist > self.deviation_threshold:
                        if window.prior_p_substitution > 0.5:
                            flags.append({
                                "type": "impossible_short",
                                "severity": "critical",
                                "description": f"Critical geometric change (dist={dist:.3f}) in <30 days."
                            })
                        else:
                            flags.append({
                                "type": "transition_anomaly",
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
                if not is_reference_period(curr.get("extracted_at")):
                    ref_photos = [p for p in bucket_photos[:i] if is_reference_period(p.get("extracted_at"))]
                    if ref_photos:
                        ref_metrics = [np.array(list(p.get("metrics", {}).values())) for p in ref_photos]
                        ref_avg = np.mean(ref_metrics, axis=0)
                        
                        dist_to_ref = float(np.linalg.norm(m2 - ref_avg))
                        dist_to_prev = float(np.linalg.norm(m2 - m1)) if m1.size > 0 else 999.0
                        
                        if dist_to_ref < dist_to_prev * RTR_RATIO and dist_to_prev > RTR_MIN_ABS_DELTA:
                            flags.append({
                                "type": "return_to_reference",
                                "severity": "critical",
                                "description": "Return to 1999-2001 baseline detected (Deepfake/Mask indicator)."
                            })

        return photos
