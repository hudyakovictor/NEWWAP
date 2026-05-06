#!/usr/bin/env python3
import sys
from pathlib import Path
import numpy as np

# Ensure backend is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.core.verdict import BayesianForensicEngine
from backend.core.longitudinal import LongitudinalModel
from backend.core.scoring import compute_true_coverage
from backend.core.cascade import aggregate_texture_flags

def test_longitudinal_prediction_interval():
    print("[TEST 1] Проверка Интервала Предсказания (L-01)...")
    # Historical observations of jaw width ratio (stable bone structure with minor age change)
    history = [0.45, 0.46, 0.45, 0.47, 0.46, 0.45, 0.46]
    new_val = 0.50 # Slightly drifted after 25 years
    
    model = LongitudinalModel(alpha=0.3)
    z_score = model.compute_prediction_interval(history, new_val, population_sigma=0.03)
    
    print(f"  Historical points: {history}")
    print(f"  New measurement:   {new_val}")
    print(f"  Resulting Z-score: {z_score:.4f}")
    
    # Corridor should not shrink to 0. Z-score should be around 1.5 - 2.5
    assert 1.0 <= z_score <= 4.0, f"Z-score out of expected age drift bounds: {z_score}"
    print("  [SUCCESS] TEST 1 PASSED!")

def test_bayesian_philosophy():
    print("[TEST 2] Проверка Философии Байеса (B-01)...")
    engine = BayesianForensicEngine(base_prior_h0=0.5, base_prior_h1=0.1, base_prior_h2=0.4)
    
    # 20 years delta
    delta_years = 20.0
    metric_delta = 0.05
    base_sigma = 0.02
    reliability = 0.9
    
    likelihoods = engine.compute_likelihoods(metric_delta, base_sigma, delta_years, reliability)
    
    print(f"  Delta years:          {delta_years}")
    print(f"  Base Prior H2:        {engine.priors[2]:.2f}")
    print(f"  Likelihood H0 (same): {likelihoods[0]:.4e}")
    print(f"  Likelihood H2 (diff): {likelihoods[2]:.4e}")
    
    # Priors must be strictly unchanged by years!
    assert engine.priors[2] == 0.4, f"A priori probability changed due to time gap: {engine.priors[2]}"
    # Likelihood for H0 should be non-zero due to time drift expansion
    assert likelihoods[0] > 1e-5, f"Likelihood H0 underflowed too aggressively: {likelihoods[0]}"
    print("  [SUCCESS] TEST 2 PASSED!")

def test_true_coverage():
    print("[TEST 3] Проверка Истинного Покрытия (M-06)...")
    # Smiling occlusion: jaw_width_ratio and nose_width_ratio are omitted
    computed_metrics = {
        "cranial_face_index": 0.55,
        "interorbital_ratio": 0.22,
        "jaw_width_ratio": np.nan, # Omitted due to smile
        "nose_width_ratio": np.nan,
    }
    pose_bucket = "frontal"
    
    coverage = compute_true_coverage(computed_metrics, pose_bucket)
    print(f"  Pose Bucket:      {pose_bucket}")
    print(f"  Metrics keys:     {list(computed_metrics.keys())}")
    print(f"  True Coverage:    {coverage:.4%}")
    
    # Frontal has about 6 expected keys, 2 are NaN, so coverage should be < 0.75
    assert coverage < 0.85, f"False 100% coverage detected: {coverage}"
    print("  [SUCCESS] TEST 3 PASSED!")

def test_weighted_silicone():
    print("[TEST 4] Проверка Взвешенной Силиконовой Агрегации...")
    # Bad shot: high silicone probability but extremely low confidence (flash glare)
    tex_a = {"silicone_probability": 0.9}
    conf_a = 0.1
    
    # Good shot: very low silicone probability with high confidence
    tex_b = {"silicone_probability": 0.05}
    conf_b = 0.9
    
    weighted_score = aggregate_texture_flags(tex_a, tex_b, conf_a, conf_b)
    print(f"  Weighted Silicone Score: {weighted_score:.4f}")
    
    # Weighted average should be close to 0.135 (low risk), far below the toxic max() of 0.9
    assert weighted_score < 0.20, f"Silicone score artificially inflated by bad frame: {weighted_score}"
    print("  [SUCCESS] TEST 4 PASSED!")

def main():
    print("=== RUNNING SMOKE-TEST ITERATION 4 ===")
    test_longitudinal_prediction_interval()
    print("-" * 40)
    test_bayesian_philosophy()
    print("-" * 40)
    test_true_coverage()
    print("-" * 40)
    test_weighted_silicone()
    print("=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    main()
