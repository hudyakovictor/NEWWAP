"""
Golden Forensic Cases for Methodology Validation.

These are controlled test cases with known ground truth to verify that
the Bayesian evidence calculation behaves correctly.

Each case specifies:
- Expected verdict (H0, H1, H2, or INSUFFICIENT_DATA)
- Expected H1 subtype (if applicable)
- Expected confidence ranges
- Input photo characteristics

Run with: python backend/tests/golden_cases.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.core.analysis import calculate_bayesian_evidence, ZONE_WEIGHTS


def create_photo_summary(
    photo_id: str,
    year: int,
    metrics: dict,
    texture: dict,
    pose: dict,
    quality: dict = None,
) -> dict:
    """Helper to create a photo summary for testing."""
    return {
        "photo_id": photo_id,
        "year": year,
        "metrics": metrics,
        "texture_forensics": texture,
        "pose": pose,
        "quality": quality or {"overall_score": 0.85},
    }


def create_natural_metrics(base_value: float = 0.75, variation: float = 0.02) -> dict:
    """Create metrics for natural (same person) case with small variations."""
    import random
    return {
        "nose_projection_ratio": base_value + random.uniform(-variation, variation),
        "orbit_depth_L_ratio": base_value + random.uniform(-variation, variation),
        "orbit_depth_R_ratio": base_value + random.uniform(-variation, variation),
        "jaw_width_ratio": base_value + random.uniform(-variation, variation),
        "cranial_face_index": base_value + random.uniform(-variation, variation),
        "chin_projection_ratio": base_value + random.uniform(-variation, variation),
        "gonial_angle_L": 0.72 + random.uniform(-variation, variation),
        "gonial_angle_R": 0.71 + random.uniform(-variation, variation),
        "canthal_tilt_L": 0.65 + random.uniform(-variation, variation),
        "canthal_tilt_R": 0.64 + random.uniform(-variation, variation),
        "nasofacial_angle_ratio": 0.58 + random.uniform(-variation, variation),
        "chin_offset_asymmetry": 0.05 + random.uniform(-variation/2, variation/2),
        "nasal_frontal_index": 0.48 + random.uniform(-variation, variation),
        "forehead_slope_index": 0.35 + random.uniform(-variation, variation),
        "texture_silicone_prob": 0.05 + random.uniform(-0.03, 0.05),
        "texture_pore_density": 42 + random.uniform(-5, 5),
        "nose_width_ratio": 0.38 + random.uniform(-variation, variation),
        "texture_wrinkle_forehead": 0.22 + random.uniform(-0.05, 0.05),
        "texture_wrinkle_nasolabial": 0.28 + random.uniform(-0.05, 0.05),
        "texture_spot_density": 0.35 + random.uniform(-0.05, 0.05),
        "texture_global_smoothness": 0.55 + random.uniform(-0.05, 0.05),
        "interorbital_ratio": 0.45 + random.uniform(-variation, variation),
        "reliability_weight": 0.85,
    }


def create_synthetic_metrics(base_value: float = 0.75) -> dict:
    """Create metrics for synthetic/mask case."""
    return {
        "nose_projection_ratio": base_value,
        "orbit_depth_L_ratio": base_value,
        "orbit_depth_R_ratio": base_value,
        "jaw_width_ratio": base_value,
        "cranial_face_index": base_value,
        "chin_projection_ratio": base_value,
        "gonial_angle_L": 0.72,
        "gonial_angle_R": 0.71,
        "canthal_tilt_L": 0.65,
        "canthal_tilt_R": 0.64,
        "nasofacial_angle_ratio": 0.58,
        "chin_offset_asymmetry": 0.03,
        "nasal_frontal_index": 0.48,
        "forehead_slope_index": 0.35,
        "texture_silicone_prob": 0.65,  # High synthetic probability
        "texture_pore_density": 15,  # Low pore density (smooth)
        "nose_width_ratio": 0.38,
        "texture_wrinkle_forehead": 0.05,  # Few wrinkles
        "texture_wrinkle_nasolabial": 0.08,
        "texture_spot_density": 0.15,
        "texture_global_smoothness": 0.85,  # Very smooth
        "interorbital_ratio": 0.45,
        "reliability_weight": 0.75,
    }


def create_different_person_metrics() -> dict:
    """Create metrics for clearly different person."""
    return {
        "nose_projection_ratio": 0.45,  # Very different
        "orbit_depth_L_ratio": 0.85,
        "orbit_depth_R_ratio": 0.82,
        "jaw_width_ratio": 0.95,  # Wide jaw
        "cranial_face_index": 0.75,
        "chin_projection_ratio": 0.35,
        "gonial_angle_L": 0.85,
        "gonial_angle_R": 0.82,
        "canthal_tilt_L": 0.55,
        "canthal_tilt_R": 0.75,  # Asymmetric
        "nasofacial_angle_ratio": 0.48,
        "chin_offset_asymmetry": 0.25,  # High asymmetry
        "nasal_frontal_index": 0.38,
        "forehead_slope_index": 0.45,
        "texture_silicone_prob": 0.15,
        "texture_pore_density": 38,
        "nose_width_ratio": 0.48,
        "texture_wrinkle_forehead": 0.25,
        "texture_wrinkle_nasolabial": 0.30,
        "texture_spot_density": 0.40,
        "texture_global_smoothness": 0.50,
        "interorbital_ratio": 0.55,  # Different
        "reliability_weight": 0.80,
    }


# Golden Cases Definitions
GOLDEN_CASES = [
    {
        "id": "GC-001",
        "name": "Same person, same year, neutral expression",
        "description": "Two photos of the same person taken within the same year, both with neutral expressions",
        "photo_a": {
            "year": 2020,
            "metrics_factory": lambda: create_natural_metrics(0.75, 0.02),
            "texture": {
                "silicone_probability": 0.08,
                "fft_high_freq_ratio": 0.42,
                "albedo_uniformity": 0.65,
                "specular_gloss": 0.38,
                "lbp_complexity": 2.9,
                "lbp_uniformity": 0.42,
                "pore_density": 45,
                "wrinkle_forehead": 0.24,
                "wrinkle_nasolabial": 0.30,
            },
            "pose": {"yaw": 5, "pitch": 2, "expression": "neutral"},
        },
        "photo_b": {
            "year": 2020,
            "metrics_factory": lambda: create_natural_metrics(0.76, 0.02),
            "texture": {
                "silicone_probability": 0.10,
                "fft_high_freq_ratio": 0.44,
                "albedo_uniformity": 0.62,
                "specular_gloss": 0.40,
                "lbp_complexity": 2.8,
                "lbp_uniformity": 0.45,
                "pore_density": 43,
                "wrinkle_forehead": 0.22,
                "wrinkle_nasolabial": 0.28,
            },
            "pose": {"yaw": 3, "pitch": 1, "expression": "neutral"},
        },
        "expected": {
            "verdict": "H0",
            "min_posterior_h0": 0.70,
            "max_posterior_h1": 0.25,
        },
    },
    {
        "id": "GC-002",
        "name": "Same person, 10 year gap, aging expected",
        "description": "Same person with 10 year time gap, should still be identified as same",
        "photo_a": {
            "year": 2010,
            "metrics_factory": lambda: create_natural_metrics(0.75, 0.02),
            "texture": {
                "silicone_probability": 0.05,
                "fft_high_freq_ratio": 0.40,
                "albedo_uniformity": 0.70,
                "specular_gloss": 0.35,
                "lbp_complexity": 3.2,
                "lbp_uniformity": 0.38,
                "pore_density": 48,
                "wrinkle_forehead": 0.15,
                "wrinkle_nasolabial": 0.22,
            },
            "pose": {"yaw": 5, "pitch": 2, "expression": "neutral"},
        },
        "photo_b": {
            "year": 2020,
            "metrics_factory": lambda: create_natural_metrics(0.74, 0.03),  # Slightly more variation
            "texture": {
                "silicone_probability": 0.12,
                "fft_high_freq_ratio": 0.45,
                "albedo_uniformity": 0.60,
                "specular_gloss": 0.42,
                "lbp_complexity": 2.6,
                "lbp_uniformity": 0.48,
                "pore_density": 38,
                "wrinkle_forehead": 0.35,  # More wrinkles (aging)
                "wrinkle_nasolabial": 0.40,  # More wrinkles
            },
            "pose": {"yaw": 8, "pitch": 3, "expression": "neutral"},
        },
        "expected": {
            "verdict": "H0",
            "min_posterior_h0": 0.60,
            "max_posterior_h1": 0.30,
        },
    },
    {
        "id": "GC-003",
        "name": "Physical mask detection",
        "description": "Photo with physical silicone mask, should be detected as H1-mask",
        "photo_a": {
            "year": 2020,
            "metrics_factory": lambda: create_natural_metrics(0.75, 0.02),
            "texture": {
                "silicone_probability": 0.08,
                "fft_high_freq_ratio": 0.42,
                "albedo_uniformity": 0.65,
                "specular_gloss": 0.38,
                "lbp_complexity": 2.9,
                "lbp_uniformity": 0.42,
                "pore_density": 45,
                "wrinkle_forehead": 0.24,
                "wrinkle_nasolabial": 0.30,
            },
            "pose": {"yaw": 5, "pitch": 2, "expression": "neutral"},
        },
        "photo_b": {
            "year": 2020,
            "metrics_factory": create_synthetic_metrics,
            "texture": {
                "silicone_probability": 0.72,
                "fft_high_freq_ratio": 0.48,
                "albedo_uniformity": 0.55,
                "specular_gloss": 0.75,  # High specular (plastic-like)
                "lbp_complexity": 1.2,
                "lbp_uniformity": 0.75,  # High uniformity
                "pore_density": 12,  # Very low
                "wrinkle_forehead": 0.03,
                "wrinkle_nasolabial": 0.05,
            },
            "pose": {"yaw": 6, "pitch": 2, "expression": "neutral"},
        },
        "expected": {
            "verdict": "H1",
            "min_posterior_h1": 0.60,
            "expected_subtype": "mask",
        },
    },
    {
        "id": "GC-004",
        "name": "Different persons",
        "description": "Two clearly different people",
        "photo_a": {
            "year": 2020,
            "metrics_factory": lambda: create_natural_metrics(0.75, 0.02),
            "texture": {
                "silicone_probability": 0.10,
                "fft_high_freq_ratio": 0.42,
                "albedo_uniformity": 0.65,
                "specular_gloss": 0.38,
                "lbp_complexity": 2.9,
                "lbp_uniformity": 0.42,
                "pore_density": 45,
                "wrinkle_forehead": 0.24,
                "wrinkle_nasolabial": 0.30,
            },
            "pose": {"yaw": 5, "pitch": 2, "expression": "neutral"},
        },
        "photo_b": {
            "year": 2020,
            "metrics_factory": create_different_person_metrics,
            "texture": {
                "silicone_probability": 0.15,
                "fft_high_freq_ratio": 0.45,
                "albedo_uniformity": 0.62,
                "specular_gloss": 0.42,
                "lbp_complexity": 2.7,
                "lbp_uniformity": 0.45,
                "pore_density": 40,
                "wrinkle_forehead": 0.28,
                "wrinkle_nasolabial": 0.32,
            },
            "pose": {"yaw": 7, "pitch": 3, "expression": "neutral"},
        },
        "expected": {
            "verdict": "H2",
            "min_posterior_h2": 0.55,
        },
    },
    {
        "id": "GC-005",
        "name": "Insufficient data - missing metrics",
        "description": "Very few zones available, should return INSUFFICIENT_DATA",
        "photo_a": {
            "year": 2020,
            "metrics_factory": lambda: {
                "nose_projection_ratio": 0.75,
                "texture_silicone_prob": 0.15,
                "reliability_weight": 0.80,
            },  # Only 2 zones
            "texture": {
                "silicone_probability": 0.15,
                "fft_high_freq_ratio": 0.45,
                "albedo_uniformity": 0.60,
                "specular_gloss": 0.40,
                "lbp_complexity": 2.5,
                "lbp_uniformity": 0.48,
                "pore_density": 40,
                "wrinkle_forehead": 0.20,
                "wrinkle_nasolabial": 0.25,
            },
            "pose": {"yaw": 5, "pitch": 2, "expression": "neutral"},
        },
        "photo_b": {
            "year": 2020,
            "metrics_factory": lambda: {
                "nose_projection_ratio": 0.76,
                "texture_silicone_prob": 0.12,
                "reliability_weight": 0.75,
            },  # Only 2 zones
            "texture": {
                "silicone_probability": 0.12,
                "fft_high_freq_ratio": 0.42,
                "albedo_uniformity": 0.62,
                "specular_gloss": 0.38,
                "lbp_complexity": 2.8,
                "lbp_uniformity": 0.45,
                "pore_density": 42,
                "wrinkle_forehead": 0.22,
                "wrinkle_nasolabial": 0.28,
            },
            "pose": {"yaw": 6, "pitch": 3, "expression": "neutral"},
        },
        "expected": {
            "verdict": "INSUFFICIENT_DATA",
            "max_coverage": 0.15,
        },
    },
]


def run_golden_case(case: dict) -> dict:
    """Run a single golden case and return results."""
    a = create_photo_summary(
        f"{case['id']}_A",
        case["photo_a"]["year"],
        case["photo_a"]["metrics_factory"](),
        case["photo_a"]["texture"],
        case["photo_a"]["pose"],
    )
    b = create_photo_summary(
        f"{case['id']}_B",
        case["photo_b"]["year"],
        case["photo_b"]["metrics_factory"](),
        case["photo_b"]["texture"],
        case["photo_b"]["pose"],
    )
    
    result = calculate_bayesian_evidence(a, b)
    
    # Validate expectations
    passed = True
    failures = []
    
    if "verdict" in case["expected"]:
        if result["verdict"] != case["expected"]["verdict"]:
            passed = False
            failures.append(f"Expected verdict {case['expected']['verdict']}, got {result['verdict']}")
    
    if "min_posterior_h0" in case["expected"]:
        if result["posteriors"]["H0"] < case["expected"]["min_posterior_h0"]:
            passed = False
            failures.append(f"H0 posterior {result['posteriors']['H0']:.3f} below minimum {case['expected']['min_posterior_h0']}")
    
    if "max_posterior_h1" in case["expected"]:
        if result["posteriors"]["H1"] > case["expected"]["max_posterior_h1"]:
            passed = False
            failures.append(f"H1 posterior {result['posteriors']['H1']:.3f} above maximum {case['expected']['max_posterior_h1']}")
    
    if "min_posterior_h1" in case["expected"]:
        if result["posteriors"]["H1"] < case["expected"]["min_posterior_h1"]:
            passed = False
            failures.append(f"H1 posterior {result['posteriors']['H1']:.3f} below minimum {case['expected']['min_posterior_h1']}")
    
    if "min_posterior_h2" in case["expected"]:
        if result["posteriors"]["H2"] < case["expected"]["min_posterior_h2"]:
            passed = False
            failures.append(f"H2 posterior {result['posteriors']['H2']:.3f} below minimum {case['expected']['min_posterior_h2']}")
    
    if "expected_subtype" in case["expected"]:
        subtype = result.get("texture", {}).get("h1Subtype", {}).get("primary")
        if subtype != case["expected"]["expected_subtype"]:
            passed = False
            failures.append(f"Expected H1 subtype {case['expected']['expected_subtype']}, got {subtype}")
    
    if "max_coverage" in case["expected"]:
        coverage = result.get("dataQuality", {}).get("coverageRatio", 1.0)
        if coverage > case["expected"]["max_coverage"]:
            passed = False
            failures.append(f"Coverage {coverage:.2f} above maximum {case['expected']['max_coverage']}")
    
    return {
        "case": case,
        "result": result,
        "passed": passed,
        "failures": failures,
    }


def main():
    """Run all golden cases and report results."""
    print("\n" + "=" * 70)
    print("GOLDEN FORENSIC CASES - Methodology Validation")
    print("=" * 70 + "\n")
    
    passed = 0
    failed = 0
    
    for case in GOLDEN_CASES:
        print(f"Running {case['id']}: {case['name']}")
        print(f"  {case['description']}")
        
        result = run_golden_case(case)
        
        if result["passed"]:
            print(f"  ✓ PASSED")
            print(f"    Verdict: {result['result']['verdict']}")
            print(f"    Posteriors: H0={result['result']['posteriors']['H0']:.3f}, "
                  f"H1={result['result']['posteriors']['H1']:.3f}, "
                  f"H2={result['result']['posteriors']['H2']:.3f}")
            if result['result'].get('texture', {}).get('h1Subtype'):
                subtype = result['result']['texture']['h1Subtype']
                print(f"    H1 Subtype: {subtype['primary']} (conf: {subtype['confidence']:.2f})")
            passed += 1
        else:
            print(f"  ✗ FAILED")
            for failure in result["failures"]:
                print(f"    - {failure}")
            failed += 1
        
        print()
    
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(GOLDEN_CASES)} cases")
    print("=" * 70 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
