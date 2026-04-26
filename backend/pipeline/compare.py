from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .types import ComparisonResult, ReconstructionResult, VisibilityResult, AlignmentResult
from .alignment import rigid_umeyama, gpa_unit_scale
from .scoring import align_and_score, extract_macro_bone_metrics
from .visibility import compute_visibility
from .calibration import CalibrationAnalyzer
from .zones import MACRO_BONE_INDICES, compute_zone_metrics, provisional_band_from_score
from core.constants import ALIGNMENT_MIN_RANK
from core.utils import iso_now, json_ready

def _extract_calibrated_geometry_evidence(
    calibration: CalibrationAnalyzer,
    raw_error: float,
    robust_error: float,
    pose_delta: float,
) -> Dict[str, float]:
    """
    Best-effort extraction of calibrated geometry evidence.
    Falls back to a stable proxy when no dedicated calibration API is available.
    """
    signal = float(max(robust_error, 0.0))
    noise = float(max(raw_error - robust_error, 0.0))
    snr = 0.0
    evidence_mode = "fallback"

    for method_name in ("decompose_comparison", "estimate_geometry_evidence", "estimate_snr"):
        method = getattr(calibration, method_name, None)
        if not callable(method):
            continue

        candidate = None
        for kwargs in (
            {"raw_error": raw_error, "pose_delta": pose_delta},
            {"error": raw_error, "pose_delta": pose_delta},
            {"raw_error": raw_error},
            {"error": raw_error},
        ):
            try:
                candidate = method(**kwargs)
                break
            except TypeError:
                continue
            except Exception:
                candidate = None
                break

        if candidate is None:
            continue

        if isinstance(candidate, dict):
            signal = float(candidate.get("signal", candidate.get("signal_error", signal)))
            noise = float(candidate.get("noise", candidate.get("predicted_noise", noise)))
            snr = float(candidate.get("snr", candidate.get("signal_to_noise_ratio", snr)))
        else:
            signal = float(getattr(candidate, "signal", getattr(candidate, "signal_error", signal)))
            noise = float(getattr(candidate, "noise", getattr(candidate, "predicted_noise", noise)))
            snr = float(getattr(candidate, "snr", getattr(candidate, "signal_to_noise_ratio", snr)))
        evidence_mode = "calibrated"
        break

    if snr <= 0.0:
        baseline_noise = max(noise, 0.01)
        snr = float(max(signal - baseline_noise, 0.0) / baseline_noise)

    return {
        "geometry_signal": float(signal),
        "geometry_noise": float(max(noise, 0.0)),
        "geometry_snr": float(max(snr, 0.0)),
        "geometry_evidence_mode": evidence_mode,
    }

def shared_vertex_indices(vis_a: VisibilityResult, vis_b: VisibilityResult) -> np.ndarray:
    """Intersection of visible vertices."""
    shared = vis_a.binary_mask & vis_b.binary_mask
    return np.where(shared)[0]

def _estimate_face_scale(points: np.ndarray) -> float:
    """Estimate face scale from point cloud span using percentiles."""
    if points.size == 0: return 1.0
    ranges = []
    for axis in range(3):
        q75, q25 = np.percentile(points[:, axis], [75, 25])
        ranges.append(q75 - q25)
    return max(max(ranges), 1e-6)

class PairComparisonEngine:
    """
    [ITER-4] Pairwise Forensic Comparison Engine.
    Orchestrates the full flow for two reconstructions.
    """
    def __init__(self, calibration: Optional[CalibrationAnalyzer] = None):
        self.calibration = calibration or CalibrationAnalyzer()

    def compare(
        self, 
        recon_a: ReconstructionResult, 
        recon_b: ReconstructionResult,
        visibility_angle_threshold: float = 82.0
    ) -> ComparisonResult:
        # 1. Visibility & Shared Indices
        vis_a = compute_visibility(recon_a, visibility_angle_threshold)
        vis_b = compute_visibility(recon_b, visibility_angle_threshold)
        shared_idx = shared_vertex_indices(vis_a, vis_b)
        
        # 2. Pose Delta (Gimbal Lock safe compute would be here)
        # For now, simple diff of angles_deg
        pose_delta_vec = np.abs(recon_a.angles_deg - recon_b.angles_deg)
        pose_delta = float(np.linalg.norm(pose_delta_vec))

        if shared_idx.size < ALIGNMENT_MIN_RANK:
            diagnostics = {
                "pose_delta": pose_delta,
                "shared_visible_count": int(shared_idx.size),
                "visible_count_a": int(vis_a.visible_count),
                "visible_count_b": int(vis_b.visible_count),
                "failure_reason": "insufficient_shared_visibility",
                "generated_at": iso_now(),
            }
            return ComparisonResult(
                status="insufficient_shared_visibility",
                shared_vertex_indices=shared_idx,
                score_raw=None,
                score_bounded=None,
                robust_score_raw=None,
                robust_score_bounded=None,
                provisional_band="insufficient_data",
                robust_provisional_band="insufficient_data",
                visibility_a=vis_a,
                visibility_b=vis_b,
                alignment=None,
                zones=[],
                diagnostics=diagnostics,
            )

        # 3. Unit Scale Procrustes (GPA)
        # Normalize both to unit scale based on shared vertices
        _, scale_a, centroid_a = gpa_unit_scale(recon_a.vertices_world[shared_idx])
        _, scale_b, centroid_b = gpa_unit_scale(recon_b.vertices_world[shared_idx])
        
        points_a_unit = (recon_a.vertices_world - centroid_a) / (scale_a + 1e-8)
        points_b_unit = (recon_b.vertices_world - centroid_b) / (scale_b + 1e-8)
        
        # 4. Alignment & Scoring
        # Weights: combine visibility cosines
        weights = np.minimum(vis_a.cosine_weights[shared_idx], vis_b.cosine_weights[shared_idx])
        
        alignment, err, score, r_err, r_score, plane_normal = align_and_score(
            points_a_unit[shared_idx],
            points_b_unit[shared_idx],
            weights=weights
        )
        
        # 5. Zone Analysis
        zones = compute_zone_metrics(
            recon_a=recon_a,
            recon_b=recon_b,
            shared_indices=shared_idx,
            aligned_points_a=alignment.source_aligned,
            points_b=points_b_unit[shared_idx],
            shared_weights=weights,
            plane_normal=plane_normal
        )
        
        # 6. Noise Decomposition (Calibration)
        # decompose_comparison would be called here if available
        
        geometry_evidence = _extract_calibrated_geometry_evidence(
            self.calibration,
            raw_error=err,
            robust_error=r_err,
            pose_delta=pose_delta,
        )

        diagnostics = {
            "pose_delta": pose_delta,
            "face_scale_a": scale_a,
            "face_scale_b": scale_b,
            "geometry_signal": geometry_evidence["geometry_signal"],
            "geometry_noise": geometry_evidence["geometry_noise"],
            "geometry_snr": geometry_evidence["geometry_snr"],
            "geometry_evidence_mode": geometry_evidence["geometry_evidence_mode"],
            "generated_at": iso_now()
        }
        
        return ComparisonResult(
            status="ok",
            shared_vertex_indices=shared_idx,
            score_raw=err,
            score_bounded=score,
            robust_score_raw=r_err,
            robust_score_bounded=r_score,
            provisional_band=provisional_band_from_score(err),
            robust_provisional_band=provisional_band_from_score(r_err),
            visibility_a=vis_a,
            visibility_b=vis_b,
            alignment=alignment,
            zones=zones,
            diagnostics=diagnostics
        )
