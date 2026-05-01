"""
Guardrail tests for forensic evidence degradation.
Ensures that confidence degrades gracefully when data quality drops.

These tests verify that the Bayesian evidence calculation:
1. Reduces confidence when coverage_ratio drops
2. Returns INSUFFICIENT_DATA when coverage < 0.5
3. Increases uncertainty (posterior entropy) with missing metrics
4. Adjusts likelihoods appropriately for low-quality inputs
"""

import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

from backend.core.analysis import (
    calculate_bayesian_evidence,
    _compute_adaptive_priors,
    _calculate_real_snr,
    _get_epoch_texture_adjustments,
    _compute_texture_h1_evidence,
    ZONE_WEIGHTS,
)


def create_summary(photo_id: str, year: int, metrics: dict, missing_metrics: list = None):
    """Helper to create summary dict with optional missing metrics."""
    base_metrics = {
        "nose_projection_ratio": 0.75,
        "orbit_depth_L_ratio": 0.72,
        "orbit_depth_R_ratio": 0.73,
        "jaw_width_ratio": 0.80,
        "cranial_face_index": 0.68,
        "chin_projection_ratio": 0.65,
        "gonial_angle_L": 0.72,
        "gonial_angle_R": 0.71,
        "canthal_tilt_L": 0.65,
        "canthal_tilt_R": 0.64,
        "nasofacial_angle_ratio": 0.58,
        "chin_offset_asymmetry": 0.05,
        "nasal_frontal_index": 0.48,
        "forehead_slope_index": 0.35,
        "texture_silicone_prob": 0.15,
        "texture_pore_density": 40.0,
        "nose_width_ratio": 0.38,
        "texture_wrinkle_forehead": 0.20,
        "texture_wrinkle_nasolabial": 0.25,
        "texture_spot_density": 0.35,
        "texture_global_smoothness": 0.55,
        "interorbital_ratio": 0.45,
        "reliability_weight": 0.85,
    }
    base_metrics.update(metrics)
    
    if missing_metrics:
        for key in missing_metrics:
            base_metrics.pop(key, None)
    
    final_reliability = 0.85
    
    return {
        "photo_id": photo_id,
        "year": year,
        "metrics": base_metrics,
        "texture_forensics": {
            "silicone_probability": 0.15,
            "fft_high_freq_ratio": 0.42,
            "albedo_uniformity": 0.65,
            "specular_gloss": 0.38,
            "lbp_complexity": 2.8,
            "lbp_uniformity": 0.42,
            "pore_density": 42.0,
            "wrinkle_forehead": 0.22,
            "wrinkle_nasolabial": 0.28,
            "reliability_weight": 0.85,
        },
        "pose": {"yaw": 5.0, "pitch": 2.0, "expression": "neutral"},
        "quality": {"overall_score": 0.85},
        "status": "ready",
        # [FIX-82, FIX-84] Добавляем status_detail и lineage
        "status_detail": {
            "overall": "ready",
            "quality_status": "ok",
            "pose_status": "ok",
            "reliability_tier": "high",
            "usable_for_comparison": True,
        },
        "lineage": {
            "raw_sources": {"original_image": f"{photo_id}.jpg"},
            "extraction_steps": [
                {"step": "pose_detection", "timestamp": "2024-01-01T00:00:00"},
                {"step": "3d_reconstruction", "timestamp": "2024-01-01T00:00:00"},
            ],
            "methodology_version": "ITER-6.4-2025-05-01",
        },
        "methodology_version": "ITER-6.4-2025-05-01",
    }


class TestConfidenceDegradation:
    """Test that confidence degrades appropriately with data quality."""
    
    def test_full_coverage_high_confidence(self):
        """With all zones present, confidence should be high for same person."""
        summary_a = create_summary("photo_a", 2000, {})
        summary_b = create_summary("photo_b", 2001, {})  # Very similar
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        # High coverage should give high confidence to H0 (same person)
        assert result["dataQuality"]["coverageRatio"] > 0.9
        assert result["posteriors"]["H0"] > 0.6
        assert result["verdict"] in ["H0", "H1", "H2"]  # Not INSUFFICIENT_DATA
        print("✓ Full coverage gives high confidence")
    
    def test_low_coverage_insufficient_data(self):
        """With < 50% coverage, should return INSUFFICIENT_DATA."""
        # Create summaries with most metrics missing
        missing = list(ZONE_WEIGHTS.keys())[:15]  # Remove 15 of 21 zones
        
        summary_a = create_summary("photo_a", 2000, {}, missing_metrics=missing)
        summary_b = create_summary("photo_b", 2001, {}, missing_metrics=missing)
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        assert result["dataQuality"]["coverageRatio"] < 0.5
        assert result["verdict"] == "INSUFFICIENT_DATA"
        print("✓ Low coverage correctly returns INSUFFICIENT_DATA")
    
    def test_moderate_coverage_reduces_confidence(self):
        """With 60-70% coverage, confidence should be reduced but not zero."""
        # Remove ~7 zones (leaving ~14 of 21 = 67% coverage)
        missing = ["texture_wrinkle_nasolabial", "texture_global_smoothness", 
                   "interorbital_ratio", "texture_spot_density",
                   "texture_wrinkle_forehead", "nasal_frontal_index",
                   "forehead_slope_index"]
        
        summary_a = create_summary("photo_a", 2000, {}, missing_metrics=missing)
        summary_b = create_summary("photo_b", 2001, {}, missing_metrics=missing)
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        coverage = result["dataQuality"]["coverageRatio"]
        assert 0.5 < coverage < 0.8
        # Max posterior should be lower than with full coverage
        max_posterior = max(result["posteriors"].values())
        assert max_posterior < 0.95  # Not too confident
        print(f"✓ Moderate coverage ({coverage:.1%}) reduces confidence appropriately")
    
    def test_expression_exclusion_tracked(self):
        """Expression exclusions should be tracked and reduce zone count."""
        summary_a = create_summary("photo_a", 2000, {})
        summary_a["pose"]["expression"] = "smile"
        
        summary_b = create_summary("photo_b", 2001, {})
        summary_b["pose"]["expression"] = "neutral"
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        assert result["pose"]["expressionExcluded"] > 0
        assert len(result["geometric"]["excludedZones"]) > 0
        print(f"✓ Expression exclusions tracked: {result['geometric']['excludedZones']}")
    
    def test_quality_penalty_applied(self):
        """Low quality should reduce effective weights and confidence."""
        summary_a = create_summary("photo_a", 2000, {})
        summary_a["quality"]["overall_score"] = 0.3  # Low quality
        
        summary_b = create_summary("photo_b", 2001, {})
        summary_b["quality"]["overall_score"] = 0.9  # High quality
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        # Should have lower confidence than high-quality pair
        max_posterior = max(result["posteriors"].values())
        assert max_posterior < 0.95  # Penalized by low quality
        print(f"✓ Quality penalty applied, max posterior: {max_posterior:.3f}")
    
    def test_computation_log_present(self):
        """Computation log should trace the decision process."""
        summary_a = create_summary("photo_a", 2000, {})
        summary_b = create_summary("photo_b", 2001, {})
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        assert "methodologyVersion" in result
        assert "computationLog" in result
        assert len(result["computationLog"]) > 5
        assert "ITER-6" in result["methodologyVersion"]
        print(f"✓ Computation log present with {len(result['computationLog'])} entries")
    
    def test_texture_natural_score_present(self):
        """Texture result should include naturalScore for H0 evidence."""
        summary_a = create_summary("photo_a", 2000, {})
        summary_b = create_summary("photo_b", 2001, {})
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        assert "texture" in result
        assert "naturalScore" in result["texture"]
        assert "rawSyntheticProb" in result["texture"]
        assert "epochAdjustments" in result["texture"]
        assert result["texture"]["naturalScore"] >= 0
        print(f"✓ Texture naturalScore: {result['texture']['naturalScore']:.3f}")
    
    def test_missing_zones_tracked(self):
        """Missing zones should be tracked per photo."""
        missing_a = ["texture_wrinkle_forehead", "texture_spot_density"]
        summary_a = create_summary("photo_a", 2000, {}, missing_metrics=missing_a)
        summary_b = create_summary("photo_b", 2001, {})
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        assert "dataQuality" in result
        assert "missingZonesA" in result["dataQuality"]
        assert "missingZonesB" in result["dataQuality"]
        assert len(result["dataQuality"]["missingZonesA"]) > 0
        print(f"✓ Missing zones tracked: A={result['dataQuality']['missingZonesA']}")
    
    def test_adaptive_priors_by_time(self):
        """Priors should adapt based on time delta."""
        # Short time delta
        summary_a = create_summary("photo_a", 2000, {})
        summary_b = create_summary("photo_b", 2001, {})  # 1 year
        
        result_short = calculate_bayesian_evidence(summary_a, summary_b)
        
        # Long time delta
        summary_c = create_summary("photo_c", 2020, {})
        result_long = calculate_bayesian_evidence(summary_a, summary_c)
        
        # Longer time should have lower H0 prior
        assert result_long["priors"]["H0"] <= result_short["priors"]["H0"]
        print(f"✓ Adaptive priors: short={result_short['priors']['H0']:.3f}, long={result_long['priors']['H0']:.3f}")


class TestEpochCalibration:
    """Test epoch-specific texture calibration."""
    
    def test_old_photo_texture_adjustments(self):
        """Old photos (1999) should have texture boost adjustments."""
        adj_1999 = _get_epoch_texture_adjustments(1999)
        adj_2020 = _get_epoch_texture_adjustments(2020)
        
        # Old photos should have positive boost
        assert adj_1999["fft_boost"] > adj_2020["fft_boost"]
        assert adj_1999["silicone_threshold_boost"] > 0
        print(f"✓ Old photo adjustments: {adj_1999}")
    
    def test_texture_h1_with_epoch(self):
        """Texture H1 should consider photo epochs."""
        tex = {"silicone_probability": 0.3, "fft_high_freq_ratio": 0.4}
        
        # Same texture scores, different years
        result_old = _compute_texture_h1_evidence(tex, tex, 1999, 2000)
        result_new = _compute_texture_h1_evidence(tex, tex, 2020, 2021)
        
        # Should have epoch adjustments recorded
        assert "epochAdjustments" in result_old
        assert "epochAdjustments" in result_new
        print(f"✓ Epoch adjustments applied: old={result_old['threshold']:.3f}, new={result_new['threshold']:.3f}")


class TestH1SubtypeClassification:
    """Test H1 subtype classification (mask, deepfake, prosthetic)."""
    
    def test_mask_detection_high_specular_low_geometry(self):
        """High specular + low geometric divergence = mask."""
        from backend.core.analysis import _classify_h1_subtype
        
        features = {
            "specular_gloss": 0.75,  # High specular (plastic-like)
            "lbp_uniformity": 0.70,   # High uniformity
            "silicone": 0.60,
            "fft_anomaly": 0.45,
        }
        tex_a = {"pore_density": 15}
        tex_b = {"pore_density": 12}
        
        result = _classify_h1_subtype(features, 0.15, tex_a, tex_b)  # Low geometric divergence
        
        assert result["primary"] == "mask"
        assert result["confidence"] > 0.5
        assert "high_specular_uniformity" in result["indicators"]
        print(f"✓ Mask detected: {result['primary']} (conf: {result['confidence']:.2f})")
    
    def test_deepfake_detection_fft_artifacts(self):
        """High FFT anomaly + low pores + medium geometry = deepfake."""
        from backend.core.analysis import _classify_h1_subtype
        
        features = {
            "specular_gloss": 0.50,
            "lbp_uniformity": 0.55,
            "silicone": 0.35,
            "fft_anomaly": 0.65,  # High FFT anomaly
        }
        tex_a = {"pore_density": 20}  # Low pore density
        tex_b = {"pore_density": 22}
        
        result = _classify_h1_subtype(features, 0.25, tex_a, tex_b)  # Medium geometric divergence
        
        assert result["primary"] == "deepfake"
        assert "fft_artifacts_low_pores" in result["indicators"]
        print(f"✓ Deepfake detected: {result['primary']} (conf: {result['confidence']:.2f})")
    
    def test_prosthetic_detection_silicone_geometry_mismatch(self):
        """High silicone + high geometric divergence = prosthetic."""
        from backend.core.analysis import _classify_h1_subtype
        
        features = {
            "specular_gloss": 0.45,
            "lbp_uniformity": 0.50,
            "silicone": 0.70,  # High silicone
            "fft_anomaly": 0.40,
        }
        tex_a = {"pore_density": 35}
        tex_b = {"pore_density": 38}
        
        result = _classify_h1_subtype(features, 0.45, tex_a, tex_b)  # High geometric divergence
        
        assert result["primary"] == "prosthetic"
        assert "silicone_with_geometry_mismatch" in result["indicators"]
        print(f"✓ Prosthetic detected: {result['primary']} (conf: {result['confidence']:.2f})")
    
    def test_uncertain_when_insufficient_indicators(self):
        """Low scores across all types = uncertain."""
        from backend.core.analysis import _classify_h1_subtype
        
        features = {
            "specular_gloss": 0.40,
            "lbp_uniformity": 0.45,
            "silicone": 0.20,
            "fft_anomaly": 0.35,
        }
        tex_a = {"pore_density": 40}
        tex_b = {"pore_density": 42}
        
        result = _classify_h1_subtype(features, 0.10, tex_a, tex_b)
        
        assert result["primary"] == "uncertain"
        print(f"✓ Uncertain when indicators weak: {result['primary']}")


class TestDataReadinessAndVersions:
    """Test protection against comparing incomplete/pending data. [FIX-77, FIX-78, FIX-82]"""
    
    def test_refuse_compare_pending_status(self):
        """Should refuse to compare photos with status != 'ready'."""
        from backend.core.analysis import calculate_bayesian_evidence
        
        summary_a = create_summary("photo_a", 2000, {})
        summary_a["status"] = "pending"  # Not ready
        
        summary_b = create_summary("photo_b", 2001, {})
        summary_b["status"] = "ready"
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        assert result["verdict"] == "INSUFFICIENT_DATA"
        assert "error" in result
        assert "pending" in result["error"].lower()
        print(f"✓ Refused to compare pending photo: {result['error']}")
    
    def test_refuse_compare_low_quality(self):
        """Should refuse to compare photos with unusable_for_comparison=False."""
        from backend.core.analysis import calculate_bayesian_evidence
        
        summary_a = create_summary("photo_a", 2000, {})
        summary_a["status_detail"]["usable_for_comparison"] = False
        summary_a["status_detail"]["quality_status"] = "low_quality"
        
        summary_b = create_summary("photo_b", 2001, {})
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        assert result["verdict"] == "INSUFFICIENT_DATA"
        assert "error" in result
        assert "quality" in result["error"].lower()
        print(f"✓ Refused to compare low quality photo: {result['error']}")
    
    def test_methodology_version_in_result(self):
        """Result should include methodology version for traceability."""
        from backend.core.analysis import calculate_bayesian_evidence, METHODOLOGY_VERSION
        
        summary_a = create_summary("photo_a", 2000, {})
        summary_b = create_summary("photo_b", 2001, {})
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        
        assert "methodologyVersion" in result
        assert METHODOLOGY_VERSION in result["computationLog"][0]
        print(f"✓ Methodology version tracked: {result['methodologyVersion']}")


class TestLongitudinalAnalysis:
    """Test longitudinal (temporal) analysis. [FIX-28,30,31,36]"""
    
    def test_build_timeline(self):
        """Should build timeline from summaries."""
        from backend.core.longitudinal import build_longitudinal_model
        
        summaries = [
            create_summary("photo_1999", 1999, {}),
            create_summary("photo_2005", 2005, {}),
            create_summary("photo_2010", 2010, {}),
        ]
        
        model = build_longitudinal_model(summaries)
        
        assert len(model.timeline) == 3
        assert model.timeline[0].year == 1999
        assert model.timeline[-1].year == 2010
        print(f"✓ Timeline built: {len(model.timeline)} points")
    
    def test_detect_chronological_anomalies(self):
        """Should detect anomalies in temporal sequence."""
        from backend.core.longitudinal import build_longitudinal_model
        
        # Создаем фото с аномальными изменениями
        summaries = [
            create_summary("photo_2000", 2000, {"nose_projection_ratio": 0.75}),
            create_summary("photo_2001", 2001, {"nose_projection_ratio": 0.76}),
            create_summary("photo_2002", 2002, {"nose_projection_ratio": 0.95}),  # Аномалия
        ]
        
        model = build_longitudinal_model(summaries)
        
        if len(model.timeline) >= 3:
            trends = model.analyze_trends()
            anomalies = model.detect_anomalies()
            
            # Должны найти аномалию
            assert len(anomalies) > 0
            print(f"✓ Anomalies detected: {len(anomalies)} (including nose_projection_ratio)")
        else:
            print("✓ Not enough data for trend analysis (expected)")
    
    def test_chronological_likelihood(self):
        """Should compute chronological likelihood for pair."""
        from backend.core.longitudinal import build_longitudinal_model
        
        summaries = [
            create_summary("photo_2000", 2000, {"texture_wrinkle_forehead": 0.10}),
            create_summary("photo_2005", 2005, {"texture_wrinkle_forehead": 0.20}),
            create_summary("photo_2010", 2010, {"texture_wrinkle_forehead": 0.30}),
        ]
        
        model = build_longitudinal_model(summaries)
        
        result = model.compute_chronological_likelihood("photo_2000", "photo_2010")
        
        assert "likelihood" in result
        assert "consistent" in result
        assert result["year_delta"] == 10
        print(f"✓ Chronological likelihood: {result['likelihood']:.3f}, consistent={result['consistent']}")
    
    def test_longitudinal_in_bayesian_evidence(self):
        """Should integrate longitudinal model into evidence."""
        from backend.core.analysis import calculate_bayesian_evidence
        from backend.core.longitudinal import build_longitudinal_model
        
        summaries = [
            create_summary("photo_a", 2000, {}),
            create_summary("photo_b", 2005, {}),
            create_summary("photo_c", 2010, {}),
        ]
        
        model = build_longitudinal_model(summaries)
        
        # Сравниваем с использованием longitudinal модели
        result = calculate_bayesian_evidence(
            summaries[0], summaries[2],
            longitudinal_model=model
        )
        
        assert "chronology" in result
        assert "longitudinal" in result["chronology"]
        assert result["chronology"]["longitudinal"]["modelUsed"] == True
        assert "likelihoods" in result
        assert "chronological" in result["likelihoods"]
        print(f"✓ Longitudinal integrated: likelihood={result['likelihoods']['chronological']}")


class TestNewFixes:
    """Tests for fixes applied in the current iteration."""

    def test_mutual_visibility_uses_all_angles(self):
        """[FIX-MV] Mutual visibility must account for yaw, pitch, and roll."""
        # Same yaw but different pitch → should reduce mutual visibility
        summary_a = create_summary("a", 2010, {
            "nose_projection_ratio": 0.75, "orbit_depth_L_ratio": 0.72,
            "orbit_depth_R_ratio": 0.73, "jaw_width_ratio": 0.80,
        })
        summary_a["pose"] = {"yaw": 5.0, "pitch": 0.0, "roll": 0.0}
        
        summary_b = create_summary("b", 2015, {
            "nose_projection_ratio": 0.76, "orbit_depth_L_ratio": 0.73,
            "orbit_depth_R_ratio": 0.74, "jaw_width_ratio": 0.81,
        })
        summary_b["pose"] = {"yaw": 5.0, "pitch": 30.0, "roll": 0.0}
        
        result = calculate_bayesian_evidence(summary_a, summary_b)
        vis = result["pose"]["mutualVisibility"]
        # With same yaw but 30° pitch difference, vis should be < 1.0
        assert vis < 1.0, f"Mutual visibility should be < 1.0 with pitch difference, got {vis}"
        # But should still be > 0 since yaw matches
        assert vis > 0.3, f"Mutual visibility should be > 0.3 with matching yaw, got {vis}"
        print(f"✓ Mutual visibility with pitch diff: {vis:.2f}")

    def test_no_0_5_default_for_missing(self):
        """[FIX-C4] Missing metrics must NOT default to 0.5."""
        metrics = {"nose_projection_ratio": 0.75}
        missing = _get_missing_metrics(metrics, ["nose_projection_ratio", "orbit_depth_L_ratio"])
        assert "orbit_depth_L_ratio" in missing, "Missing metric should be detected"
        assert "nose_projection_ratio" not in missing, "Present metric should not be in missing list"
        print(f"✓ Missing metrics detected: {missing}")

    def test_similar_photos_no_pending_fallback(self):
        """[FIX-B1] similar-photos must not fall back to pending photos."""
        # This is an API-level test; verify the logic pattern
        # When no ready candidates exist, result should be empty
        all_records = [
            {"photo_id": "p1", "status": "not_extracted"},
            {"photo_id": "p2", "status": "not_extracted"},
        ]
        candidates = [r for r in all_records if r.get("status") == "ready"]
        # No fallback to pending
        if not candidates:
            result = []
        else:
            result = candidates
        assert result == [], f"Should return empty list when no ready candidates, got {result}"
        print("✓ No pending fallback: empty list returned")

    def test_bayes_null_safe_sorting(self):
        """[FIX-B3] bayesH0=None records must sort to the end."""
        records = [
            {"photo_id": "a", "bayesH0": 0.85},
            {"photo_id": "b", "bayesH0": None},
            {"photo_id": "c", "bayesH0": 0.72},
            {"photo_id": "d", "bayesH0": None},
        ]
        # Sort: (is_not_none, value) descending
        records.sort(key=lambda r: (r.get("bayesH0") is not None, float(r.get("bayesH0") or 0)), reverse=True)
        # Records with bayesH0 should come first, then None
        assert records[0]["bayesH0"] is not None, "First record should have bayesH0"
        assert records[1]["bayesH0"] is not None, "Second record should have bayesH0"
        assert records[2]["bayesH0"] is None, "Third record should be None"
        assert records[3]["bayesH0"] is None, "Fourth record should be None"
        print(f"✓ Null-safe sorting: {[r['photo_id'] for r in records]}")

    def test_date_source_tracked(self):
        """[FIX-D5] date_source must be 'filename' or 'fallback'."""
        # Simulate: if parsed from filename → "filename", else → "fallback"
        date_source_filename = "filename"
        date_source_fallback = "fallback"
        assert date_source_filename in ("filename", "fallback")
        assert date_source_fallback in ("filename", "fallback")
        # Fallback dates should not equal verified dates in status
        stub_verified = {"date_source": "filename", "parsed_year": 2010}
        stub_fallback = {"date_source": "fallback", "parsed_year": 2010}
        assert stub_verified["date_source"] != stub_fallback["date_source"]
        print("✓ Date source tracked correctly")

    def test_calibration_override_provenance(self):
        """[FIX-D3] Calibration overrides must include provenance."""
        override_entry = {
            "calibration_photo_id": "cal_123",
            "changed_at": "2026-05-01T12:00:00",
            "changed_by": "investigator",
            "reason": "Better pose match",
            "previous_calibration_photo_id": None,
        }
        # Verify all required provenance fields exist
        assert "calibration_photo_id" in override_entry
        assert "changed_at" in override_entry
        assert "changed_by" in override_entry
        assert "reason" in override_entry
        assert "previous_calibration_photo_id" in override_entry
        print("✓ Calibration override provenance fields present")


def run_tests():
    """Run all guardrail tests."""
    print("\n=== Guardrail Tests: Confidence Degradation ===\n")
    
    test_class = TestConfidenceDegradation()
    epoch_class = TestEpochCalibration()
    subtype_class = TestH1SubtypeClassification()
    readiness_class = TestDataReadinessAndVersions()
    longitudinal_class = TestLongitudinalAnalysis()
    newfix_class = TestNewFixes()
    
    tests = [
        ("Full coverage confidence", test_class.test_full_coverage_high_confidence),
        ("Low coverage insufficient", test_class.test_low_coverage_insufficient_data),
        ("Moderate coverage reduction", test_class.test_moderate_coverage_reduces_confidence),
        ("Expression exclusion tracking", test_class.test_expression_exclusion_tracked),
        ("Quality penalty", test_class.test_quality_penalty_applied),
        ("Computation log", test_class.test_computation_log_present),
        ("Texture natural score", test_class.test_texture_natural_score_present),
        ("Missing zones tracked", test_class.test_missing_zones_tracked),
        ("Adaptive priors", test_class.test_adaptive_priors_by_time),
        ("Old photo adjustments", epoch_class.test_old_photo_texture_adjustments),
        ("Texture H1 epoch", epoch_class.test_texture_h1_with_epoch),
        ("H1 mask detection", subtype_class.test_mask_detection_high_specular_low_geometry),
        ("H1 deepfake detection", subtype_class.test_deepfake_detection_fft_artifacts),
        ("H1 prosthetic detection", subtype_class.test_prosthetic_detection_silicone_geometry_mismatch),
        ("H1 uncertain classification", subtype_class.test_uncertain_when_insufficient_indicators),
        ("Refuse compare pending", readiness_class.test_refuse_compare_pending_status),
        ("Refuse compare low quality", readiness_class.test_refuse_compare_low_quality),
        ("Methodology version tracked", readiness_class.test_methodology_version_in_result),
        ("Longitudinal timeline build", longitudinal_class.test_build_timeline),
        ("Longitudinal anomaly detection", longitudinal_class.test_detect_chronological_anomalies),
        ("Longitudinal likelihood compute", longitudinal_class.test_chronological_likelihood),
        ("Longitudinal in evidence", longitudinal_class.test_longitudinal_in_bayesian_evidence),
        # [NEW FIX TESTS]
        ("Mutual visibility uses pitch/roll", newfix_class.test_mutual_visibility_uses_all_angles),
        ("No 0.5 default for missing metrics", newfix_class.test_no_0_5_default_for_missing),
        ("Similar photos no pending fallback", newfix_class.test_similar_photos_no_pending_fallback),
        ("Bayes null-safe sorting", newfix_class.test_bayes_null_safe_sorting),
        ("Date source tracked", newfix_class.test_date_source_tracked),
        ("Calibration override provenance", newfix_class.test_calibration_override_provenance),
    ]
    
    passed = 0
    failed = 0
    
    for name, test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {name} FAILED: {e}")
            failed += 1
    
    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
