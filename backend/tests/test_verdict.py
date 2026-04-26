import math

import pytest

from backend.pipeline.verdict import (
    BayesianMultiHypothesisEngine,
    ForensicStatus,
    FuzzyLabel,
    GeometryEvidenceMode,
    normalize_geometry_evidence_mode,
)


def _engine() -> BayesianMultiHypothesisEngine:
    return BayesianMultiHypothesisEngine()


def _joined_reasoning(verdict) -> str:
    return " ".join(verdict.reasoning).lower()


def _assert_probability_distribution(verdict) -> None:
    probs = verdict.probabilities
    assert set(probs.keys()) == {"H0_same", "H1_swap", "H2_diff"}
    assert all(0.0 <= value <= 1.0 for value in probs.values())
    assert math.isclose(sum(probs.values()), 1.0, rel_tol=0.0, abs_tol=1e-6)


def _assert_mode_cap(verdict, mode: GeometryEvidenceMode) -> None:
    if mode == GeometryEvidenceMode.CALIBRATED:
        assert 0.0 <= verdict.confidence <= 1.0
    elif mode == GeometryEvidenceMode.FALLBACK:
        assert verdict.confidence <= 0.75
    else:
        assert verdict.confidence <= 0.50


def _assert_mode_cap(verdict, mode: GeometryEvidenceMode) -> None:
    if mode == GeometryEvidenceMode.CALIBRATED:
        assert 0.0 <= verdict.confidence <= 1.0
    elif mode == GeometryEvidenceMode.FALLBACK:
        assert verdict.confidence <= 0.75
    else:
        assert verdict.confidence <= 0.50


def _assert_mode_cap(verdict, mode: GeometryEvidenceMode) -> None:
    if mode == GeometryEvidenceMode.CALIBRATED:
        assert 0.0 <= verdict.confidence <= 1.0
    elif mode == GeometryEvidenceMode.FALLBACK:
        assert verdict.confidence <= 0.75
    else:
        assert verdict.confidence <= 0.50


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, GeometryEvidenceMode.UNAVAILABLE),
        ("unknown", GeometryEvidenceMode.UNAVAILABLE),
        ("fallback", GeometryEvidenceMode.FALLBACK),
        ("calibrated", GeometryEvidenceMode.CALIBRATED),
        (GeometryEvidenceMode.UNAVAILABLE, GeometryEvidenceMode.UNAVAILABLE),
    ],
)
def test_normalize_geometry_evidence_mode(value, expected):
    assert normalize_geometry_evidence_mode(value) == expected


@pytest.mark.parametrize(
    (
        "mode",
        "expected_status",
        "expected_label",
        "expected_flag",
        "forbidden_flag",
        "confidence_upper_bound",
        "must_contain_reasoning",
        "must_not_contain_reasoning",
    ),
    [
        (
            GeometryEvidenceMode.CALIBRATED,
            ForensicStatus.SAME_PERSON,
            FuzzyLabel.STRONGLY_MATCHING,
            None,
            "GEOMETRY_UNAVAILABLE",
            None,
            ["contributed fully", "natural-variation band"],
            ["confidence was capped", "geometry channel was disabled"],
        ),
        (
            GeometryEvidenceMode.FALLBACK,
            ForensicStatus.UNCERTAIN,
            FuzzyLabel.WEAK_EVIDENCE,
            "FALLBACK_GEOMETRY",
            "GEOMETRY_UNAVAILABLE",
            0.75,
            ["was attenuated", "downgraded", "confidence was capped at 0.75"],
            ["geometry channel was disabled"],
        ),
        (
            GeometryEvidenceMode.UNAVAILABLE,
            ForensicStatus.UNCERTAIN,
            FuzzyLabel.INSUFFICIENT_DATA,
            "GEOMETRY_UNAVAILABLE",
            "FALLBACK_GEOMETRY",
            0.50,
            ["was disabled", "confidence was capped at 0.50"],
            ["natural-variation band"],
        ),
    ],
)
def test_low_snr_policy_matrix(
    mode,
    expected_status,
    expected_label,
    expected_flag,
    forbidden_flag,
    confidence_upper_bound,
    must_contain_reasoning,
    must_not_contain_reasoning,
):
    verdict = _engine().synthesize(
        geometry_snr=0.0,
        texture_silicone_prob=0.05,
        chronology_flags=[],
        geometry_evidence_mode=mode,
    )

    _assert_probability_distribution(verdict)
    assert verdict.status == expected_status
    assert verdict.fuzzy_label == expected_label
    assert verdict.evidence_snr.geometry == 0.0
    assert verdict.evidence_snr.texture_silicone == 0.05
    assert verdict.evidence_snr.geometry_evidence_mode == mode

    if expected_flag is None:
        assert forbidden_flag not in verdict.flags
        assert "FALLBACK_GEOMETRY" not in verdict.flags
        assert "GEOMETRY_UNAVAILABLE" not in verdict.flags
    else:
        assert expected_flag in verdict.flags
        assert forbidden_flag not in verdict.flags

    if confidence_upper_bound is None:
        assert verdict.confidence > 0.80
    else:
        assert 0.0 <= verdict.confidence <= confidence_upper_bound

    joined = _joined_reasoning(verdict)
    for phrase in must_contain_reasoning:
        assert phrase in joined
    for phrase in must_not_contain_reasoning:
        assert phrase not in joined

    if mode == GeometryEvidenceMode.CALIBRATED:
        assert verdict.probabilities["H0_same"] > 0.80
    else:
        assert verdict.status == ForensicStatus.UNCERTAIN


@pytest.mark.parametrize(
    (
        "mode",
        "expected_status",
        "expected_label",
        "expected_flag",
        "confidence_upper_bound",
        "expected_h2_lower_bound",
        "required_reasoning_fragments",
    ),
    [
        (
            GeometryEvidenceMode.CALIBRATED,
            ForensicStatus.DIFFERENT_PERSON,
            FuzzyLabel.GEOMETRIC_MISMATCH,
            None,
            None,
            0.75,
            ["contributed fully", "significant geometric deviation"],
        ),
        (
            GeometryEvidenceMode.FALLBACK,
            ForensicStatus.UNCERTAIN,
            FuzzyLabel.WEAK_EVIDENCE,
            "FALLBACK_GEOMETRY",
            0.75,
            0.0,
            ["was attenuated", "significant geometric deviation", "confidence was capped at 0.75"],
        ),
        (
            GeometryEvidenceMode.UNAVAILABLE,
            ForensicStatus.UNCERTAIN,
            FuzzyLabel.INSUFFICIENT_DATA,
            "GEOMETRY_UNAVAILABLE",
            0.50,
            0.0,
            ["was disabled", "confidence was capped at 0.50"],
        ),
    ],
)
def test_high_snr_policy_matrix(
    mode,
    expected_status,
    expected_label,
    expected_flag,
    confidence_upper_bound,
    expected_h2_lower_bound,
    required_reasoning_fragments,
):
    verdict = _engine().synthesize(
        geometry_snr=10.0,
        texture_silicone_prob=0.05,
        chronology_flags=[],
        geometry_evidence_mode=mode,
    )

    _assert_probability_distribution(verdict)
    assert verdict.status == expected_status
    assert verdict.fuzzy_label == expected_label

    if expected_flag is None:
        assert "FALLBACK_GEOMETRY" not in verdict.flags
        assert "GEOMETRY_UNAVAILABLE" not in verdict.flags
        assert verdict.probabilities["H2_diff"] > expected_h2_lower_bound
    else:
        assert expected_flag in verdict.flags
        assert verdict.confidence <= confidence_upper_bound

    joined = _joined_reasoning(verdict)
    for fragment in required_reasoning_fragments:
        assert fragment in joined

    if mode == GeometryEvidenceMode.UNAVAILABLE:
        assert verdict.probabilities["H2_diff"] < 0.75
        assert "significant geometric deviation" not in joined


@pytest.mark.parametrize(
    ("mode", "expected_confidence", "expected_cap_phrase"),
    [
        (GeometryEvidenceMode.CALIBRATED, 0.97, None),
        (GeometryEvidenceMode.FALLBACK, 0.75, "confidence was capped at 0.75"),
        (GeometryEvidenceMode.UNAVAILABLE, 0.50, "confidence was capped at 0.50"),
    ],
)
def test_temporal_impossibility_overrides_candidate_but_still_respects_mode_caps(
    mode,
    expected_confidence,
    expected_cap_phrase,
):
    verdict = _engine().synthesize(
        geometry_snr=0.0,
        texture_silicone_prob=0.05,
        chronology_flags=[{"type": "impossible_short", "prior_p": 0.97}],
        geometry_evidence_mode=mode,
    )

    _assert_probability_distribution(verdict)
    assert verdict.status == ForensicStatus.IDENTITY_SWAP
    assert verdict.fuzzy_label == FuzzyLabel.IDENTITY_ANOMALY
    assert "TEMPORAL_IMPOSSIBILITY" in verdict.flags
    assert math.isclose(verdict.confidence, expected_confidence, rel_tol=0.0, abs_tol=1e-9)

    joined = _joined_reasoning(verdict)
    if expected_cap_phrase is None:
        assert "confidence was capped" not in joined
    else:
        assert expected_cap_phrase in joined


@pytest.mark.parametrize(
    ("mode", "expected_confidence", "expected_flag"),
    [
        (GeometryEvidenceMode.CALIBRATED, 0.85, None),
        (GeometryEvidenceMode.FALLBACK, 0.75, "FALLBACK_GEOMETRY"),
        (GeometryEvidenceMode.UNAVAILABLE, 0.50, "GEOMETRY_UNAVAILABLE"),
    ],
)
def test_return_to_reference_path_is_preserved_across_geometry_modes(mode, expected_confidence, expected_flag):
    verdict = _engine().synthesize(
        geometry_snr=0.0,
        texture_silicone_prob=0.05,
        chronology_flags=[{"type": "return_to_reference", "prior_p": 0.80}],
        geometry_evidence_mode=mode,
    )

    _assert_probability_distribution(verdict)
    assert verdict.status == ForensicStatus.RETURN_TO_BASELINE
    assert verdict.fuzzy_label == FuzzyLabel.IDENTITY_ANOMALY
    assert "RETURN_TO_BASELINE" in verdict.flags
    assert math.isclose(verdict.confidence, expected_confidence, rel_tol=0.0, abs_tol=1e-9)

    if expected_flag is None:
        assert "FALLBACK_GEOMETRY" not in verdict.flags
        assert "GEOMETRY_UNAVAILABLE" not in verdict.flags
    else:
        assert expected_flag in verdict.flags


@pytest.mark.parametrize(
    ("mode", "expected_phrase"),
    [
        (GeometryEvidenceMode.CALIBRATED, "contributed fully"),
        (GeometryEvidenceMode.FALLBACK, "was attenuated"),
        (GeometryEvidenceMode.UNAVAILABLE, "was disabled"),
    ],
)
def test_to_dict_and_reasoning_keep_mode_semantics(mode, expected_phrase):
    verdict = _engine().synthesize(
        geometry_snr=3.0,
        texture_silicone_prob=0.55,
        chronology_flags=[{"type": "transition_anomaly", "prior_p": 0.4}],
        geometry_evidence_mode=mode,
    )

    payload = verdict.to_dict()
    assert payload["status"] == verdict.status.value
    assert payload["fuzzy_label"] == verdict.fuzzy_label.value
    assert payload["evidence_snr"]["geometry_evidence_mode"] == mode.value
    assert math.isclose(payload["confidence"], verdict.confidence, rel_tol=0.0, abs_tol=1e-12)

    joined = _joined_reasoning(verdict)
    assert expected_phrase in joined
    assert "texture analysis indicates synthetic materials" in joined


@pytest.mark.parametrize(
    "mode",
    [
        GeometryEvidenceMode.CALIBRATED,
        GeometryEvidenceMode.FALLBACK,
        GeometryEvidenceMode.UNAVAILABLE,
    ],
)
def test_probability_distribution_and_caps_hold_across_snr_sweep(mode):
    previous_h0 = None
    sweep = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]

    for snr in sweep:
        verdict = _engine().synthesize(
            geometry_snr=snr,
            texture_silicone_prob=0.05,
            chronology_flags=[],
            geometry_evidence_mode=mode,
        )

        _assert_probability_distribution(verdict)
        _assert_mode_cap(verdict, mode)
        assert verdict.evidence_snr.geometry == snr
        assert verdict.evidence_snr.geometry_evidence_mode == mode

        current_h0 = verdict.probabilities["H0_same"]
        if previous_h0 is not None:
            assert current_h0 <= previous_h0 + 1e-9
        previous_h0 = current_h0


@pytest.mark.parametrize(
    "snr",
    [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0],
)
def test_unavailable_geometry_never_emits_hard_identity_conclusions_across_snr_sweep(snr):
    verdict = _engine().synthesize(
        geometry_snr=snr,
        texture_silicone_prob=0.05,
        chronology_flags=[],
        geometry_evidence_mode=GeometryEvidenceMode.UNAVAILABLE,
    )

    _assert_probability_distribution(verdict)
    _assert_mode_cap(verdict, GeometryEvidenceMode.UNAVAILABLE)
    assert verdict.status == ForensicStatus.UNCERTAIN
    assert verdict.fuzzy_label == FuzzyLabel.INSUFFICIENT_DATA
    assert "GEOMETRY_UNAVAILABLE" in verdict.flags
    assert verdict.probabilities["H2_diff"] < 0.75
    assert verdict.probabilities["H0_same"] < 0.80


@pytest.mark.parametrize(
    "silicone_prob, previous_silicone_prob",
    [
        (0.0, None),
        (0.25, 0.0),
        (0.5, 0.25),
        (0.75, 0.5),
        (1.0, 0.75),
    ],
)
def test_texture_signal_monotonically_increases_h1_under_calibrated_geometry(silicone_prob, previous_silicone_prob):
    verdict = _engine().synthesize(
        geometry_snr=2.0,
        texture_silicone_prob=silicone_prob,
        chronology_flags=[],
        geometry_evidence_mode=GeometryEvidenceMode.CALIBRATED,
    )

    _assert_probability_distribution(verdict)
    _assert_mode_cap(verdict, GeometryEvidenceMode.CALIBRATED)

    if previous_silicone_prob is None:
        return

    previous_verdict = _engine().synthesize(
        geometry_snr=2.0,
        texture_silicone_prob=previous_silicone_prob,
        chronology_flags=[],
        geometry_evidence_mode=GeometryEvidenceMode.CALIBRATED,
    )
    _assert_probability_distribution(previous_verdict)
    assert verdict.probabilities["H1_swap"] >= previous_verdict.probabilities["H1_swap"] - 1e-9



@pytest.mark.parametrize(
    "mode",
    [
        GeometryEvidenceMode.CALIBRATED,
        GeometryEvidenceMode.FALLBACK,
        GeometryEvidenceMode.UNAVAILABLE,
    ],
)
def test_probability_distribution_and_caps_hold_across_snr_sweep(mode):
    previous_h0 = None
    sweep = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]

    for snr in sweep:
        verdict = _engine().synthesize(
            geometry_snr=snr,
            texture_silicone_prob=0.05,
            chronology_flags=[],
            geometry_evidence_mode=mode,
        )

        _assert_probability_distribution(verdict)
        _assert_mode_cap(verdict, mode)
        assert verdict.evidence_snr.geometry == snr
        assert verdict.evidence_snr.geometry_evidence_mode == mode

        current_h0 = verdict.probabilities["H0_same"]
        if previous_h0 is not None:
            assert current_h0 <= previous_h0 + 1e-9
        previous_h0 = current_h0


@pytest.mark.parametrize(
    "snr",
    [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0],
)
def test_unavailable_geometry_never_emits_hard_identity_conclusions_across_snr_sweep(snr):
    verdict = _engine().synthesize(
        geometry_snr=snr,
        texture_silicone_prob=0.05,
        chronology_flags=[],
        geometry_evidence_mode=GeometryEvidenceMode.UNAVAILABLE,
    )

    _assert_probability_distribution(verdict)
    _assert_mode_cap(verdict, GeometryEvidenceMode.UNAVAILABLE)
    assert verdict.status == ForensicStatus.UNCERTAIN
    assert verdict.fuzzy_label == FuzzyLabel.INSUFFICIENT_DATA
    assert "GEOMETRY_UNAVAILABLE" in verdict.flags
    assert verdict.probabilities["H2_diff"] < 0.75
    assert verdict.probabilities["H0_same"] < 0.80


@pytest.mark.parametrize(
    "silicone_prob, previous_silicone_prob",
    [
        (0.0, None),
        (0.25, 0.0),
        (0.5, 0.25),
        (0.75, 0.5),
        (1.0, 0.75),
    ],
)
def test_texture_signal_monotonically_increases_h1_under_calibrated_geometry(silicone_prob, previous_silicone_prob):
    verdict = _engine().synthesize(
        geometry_snr=2.0,
        texture_silicone_prob=silicone_prob,
        chronology_flags=[],
        geometry_evidence_mode=GeometryEvidenceMode.CALIBRATED,
    )

    _assert_probability_distribution(verdict)
    _assert_mode_cap(verdict, GeometryEvidenceMode.CALIBRATED)

    if previous_silicone_prob is None:
        return

    previous_verdict = _engine().synthesize(
        geometry_snr=2.0,
        texture_silicone_prob=previous_silicone_prob,
        chronology_flags=[],
        geometry_evidence_mode=GeometryEvidenceMode.CALIBRATED,
    )
    _assert_probability_distribution(previous_verdict)
    assert verdict.probabilities["H1_swap"] >= previous_verdict.probabilities["H1_swap"] - 1e-9



@pytest.mark.parametrize(
    "mode",
    [
        GeometryEvidenceMode.CALIBRATED,
        GeometryEvidenceMode.FALLBACK,
        GeometryEvidenceMode.UNAVAILABLE,
    ],
)
def test_probability_distribution_and_caps_hold_across_snr_sweep(mode):
    previous_h0 = None
    sweep = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]

    for snr in sweep:
        verdict = _engine().synthesize(
            geometry_snr=snr,
            texture_silicone_prob=0.05,
            chronology_flags=[],
            geometry_evidence_mode=mode,
        )

        _assert_probability_distribution(verdict)
        _assert_mode_cap(verdict, mode)
        assert verdict.evidence_snr.geometry == snr
        assert verdict.evidence_snr.geometry_evidence_mode == mode

        current_h0 = verdict.probabilities["H0_same"]
        if previous_h0 is not None:
            assert current_h0 <= previous_h0 + 1e-9
        previous_h0 = current_h0


@pytest.mark.parametrize(
    "snr",
    [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0],
)
def test_unavailable_geometry_never_emits_hard_identity_conclusions_across_snr_sweep(snr):
    verdict = _engine().synthesize(
        geometry_snr=snr,
        texture_silicone_prob=0.05,
        chronology_flags=[],
        geometry_evidence_mode=GeometryEvidenceMode.UNAVAILABLE,
    )

    _assert_probability_distribution(verdict)
    _assert_mode_cap(verdict, GeometryEvidenceMode.UNAVAILABLE)
    assert verdict.status == ForensicStatus.UNCERTAIN
    assert verdict.fuzzy_label == FuzzyLabel.INSUFFICIENT_DATA
    assert "GEOMETRY_UNAVAILABLE" in verdict.flags
    assert verdict.probabilities["H2_diff"] < 0.75
    assert verdict.probabilities["H0_same"] < 0.80


@pytest.mark.parametrize(
    "silicone_prob, previous_silicone_prob",
    [
        (0.0, None),
        (0.25, 0.0),
        (0.5, 0.25),
        (0.75, 0.5),
        (1.0, 0.75),
    ],
)
def test_texture_signal_monotonically_increases_h1_under_calibrated_geometry(silicone_prob, previous_silicone_prob):
    verdict = _engine().synthesize(
        geometry_snr=2.0,
        texture_silicone_prob=silicone_prob,
        chronology_flags=[],
        geometry_evidence_mode=GeometryEvidenceMode.CALIBRATED,
    )

    _assert_probability_distribution(verdict)
    _assert_mode_cap(verdict, GeometryEvidenceMode.CALIBRATED)

    if previous_silicone_prob is None:
        return

    previous_verdict = _engine().synthesize(
        geometry_snr=2.0,
        texture_silicone_prob=previous_silicone_prob,
        chronology_flags=[],
        geometry_evidence_mode=GeometryEvidenceMode.CALIBRATED,
    )
    _assert_probability_distribution(previous_verdict)
    assert verdict.probabilities["H1_swap"] >= previous_verdict.probabilities["H1_swap"] - 1e-9

