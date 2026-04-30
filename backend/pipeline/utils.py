from __future__ import annotations

import numpy as np


def weighted_mean_abs(values: np.ndarray, weights: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    weight_sum = float(np.sum(weights))
    if weight_sum <= 1e-8:
        return float(np.mean(np.abs(values)))
    return float(np.sum(np.abs(values) * weights) / weight_sum)


def bounded_score_from_error(raw_error: float) -> float:
    return float(1.0 / (1.0 + raw_error))


def provisional_band_from_score(error: float) -> str:
    """
    [GEOM-04] Maps raw geometry error to forensic band labels.
    Thresholds are normalized to face scale.
    """
    if error < 0.015:
        return "strongly_matching"
    if error < 0.035:
        return "consistent"
    if error < 0.060:
        return "uncertain"
    if error < 0.100:
        return "weak_evidence"
    return "geometric_mismatch"
