from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .types import ComparisonResult, ReconstructionResult, VisibilityResult, AlignmentResult
from .alignment import rigid_umeyama, gpa_unit_scale, canonicalize_vertices_for_bucket
from .scoring import align_and_score, extract_macro_bone_metrics
from .visibility import compute_visibility
from .calibration import CalibrationAnalyzer, CalibrationProtocol, CalibrationDecomposition, find_calibration_match
from .zones import MACRO_BONE_INDICES, compute_zone_metrics, provisional_band_from_score
from core.constants import ALIGNMENT_MIN_RANK, VISIBILITY_ANGLE_DEG
from core.utils import iso_now, json_ready

_IPD_MAX_YAW_DEG = 30.0  # IPD валиден только если оба глаза видны


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

def _extract_calibrated_geometry_evidence(
    calibration: CalibrationProtocol,
    raw_error: float,
    robust_error: float,
    pose_delta: float,
    forced_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified extraction of calibrated geometry evidence.
    """
    evidence_mode = forced_mode if forced_mode is not None else "calibrated"
    
    if evidence_mode == "fallback":
        # Force fallback behavior
        signal = float(max(robust_error, 0.0))
        noise = float(max(raw_error - robust_error, 0.0))
        snr = _compute_linear_snr(signal, noise)
    else:
        try:
            # Call direct decompose method from CalibrationProtocol
            decomp = calibration.decompose(raw_error, pose_delta)
            signal = float(decomp.signal)
            noise = float(decomp.noise)
            snr = float(decomp.snr)
            evidence_mode = "calibrated"
        except Exception:
            # Fallback
            signal = float(max(robust_error, 0.0))
            noise = float(max(raw_error - robust_error, 0.0))
            snr = _compute_linear_snr(signal, noise)
            evidence_mode = "fallback"

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
    def __init__(
        self,
        calibration: Optional[CalibrationAnalyzer] = None,
        calib_df: Optional[pd.DataFrame] = None,
        calib_pairs_df: Optional[pd.DataFrame] = None
    ):
        self.calibration = calibration or CalibrationAnalyzer()
        self.calib_df = calib_df
        self.calib_pairs_df = calib_pairs_df

    def compare(
        self, 
        recon_a: ReconstructionResult, 
        recon_b: ReconstructionResult,
        visibility_angle_threshold: float = VISIBILITY_ANGLE_DEG
    ) -> ComparisonResult:
        # 1. Visibility & Shared Indices
        vis_a = compute_visibility(recon_a, visibility_angle_threshold)
        vis_b = compute_visibility(recon_b, visibility_angle_threshold)
        shared_idx = shared_vertex_indices(vis_a, vis_b)
        
        # 2. Pose Delta (Gimbal Lock safe geodesic compute)
        from scipy.spatial.transform import Rotation
        try:
            R_a = Rotation.from_euler('yxz', recon_a.angles_deg, degrees=True)
            R_b = Rotation.from_euler('yxz', recon_b.angles_deg, degrees=True)
            rot_vec = (R_a.inv() * R_b).as_rotvec()
            pose_delta = float(np.linalg.norm(rot_vec) * 180.0 / np.pi)
        except Exception:
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

        # 3. [ITER-2] Канонизируем вершины к позе бакета ДО масштабирования.
        # Нейтрализует pitch, roll и нормализует yaw — сравнение становится инвариантным к позе.
        view_group_a = getattr(recon_a, 'pose_bucket', 'frontal') or 'frontal'
        try:
            verts_a_canon = canonicalize_vertices_for_bucket(
                recon_a.vertices_world, recon_a.angles_deg, view_group_a
            )
            verts_b_canon = canonicalize_vertices_for_bucket(
                recon_b.vertices_world, recon_b.angles_deg, view_group_a  # b выравнивается к бакету a
            )
        except Exception:
            verts_a_canon = recon_a.vertices_world
            verts_b_canon = recon_b.vertices_world

        _, scale_a_gpa, centroid_a = gpa_unit_scale(verts_a_canon[shared_idx])
        _, scale_b_gpa, centroid_b = gpa_unit_scale(verts_b_canon[shared_idx])

        landmarks_available = False
        geometry_evidence_mode = "calibrated"

        _yaw_a = float(recon_a.angles_deg[1])
        _yaw_b = float(recon_b.angles_deg[1])
        _ipd_usable = abs(_yaw_a) < _IPD_MAX_YAW_DEG and abs(_yaw_b) < _IPD_MAX_YAW_DEG

        if (_ipd_usable and
            recon_a.landmarks_106 is not None and len(recon_a.landmarks_106) >= 48 and
            recon_b.landmarks_106 is not None and len(recon_b.landmarks_106) >= 48):
            try:
                lm_a = recon_a.landmarks_106
                lm_b = recon_b.landmarks_106
                le_a = lm_a[66:74].mean(0)
                re_a = lm_a[75:83].mean(0)
                scale_a_ipd = float(np.linalg.norm(le_a - re_a))
                le_b = lm_b[66:74].mean(0)
                re_b = lm_b[75:83].mean(0)
                scale_b_ipd = float(np.linalg.norm(le_b - re_b))
                if scale_a_ipd > 1e-6 and scale_b_ipd > 1e-6:
                    landmarks_available = True
                    scale_a = scale_a_ipd
                    scale_b = scale_b_ipd
            except Exception:
                pass

        if not landmarks_available:
            scale_a = scale_a_gpa
            scale_b = scale_b_gpa
            geometry_evidence_mode = "fallback"

        # [ITER-2] Используем канонические вершины вместо сырых world vertices
        points_a_unit = (verts_a_canon - centroid_a) / (scale_a + 1e-8)
        points_b_unit = (verts_b_canon - centroid_b) / (scale_b + 1e-8)
        
        # 4. Alignment & Scoring
        # Weights: combine visibility cosines
        weights = np.minimum(vis_a.cosine_weights[shared_idx], vis_b.cosine_weights[shared_idx])
        
        alignment, err, score, r_err, r_score, plane_normal = align_and_score(
            points_a_unit[shared_idx],
            points_b_unit[shared_idx],
            weights=weights,
            alignment_weights=weights
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
        geometry_evidence = _extract_calibrated_geometry_evidence(
            self.calibration,
            raw_error=err,
            robust_error=r_err,
            pose_delta=pose_delta,
            forced_mode=geometry_evidence_mode,
        )

        # Локальный noise model из nearest-K калибровочных условий
        if self.calib_df is not None and self.calib_pairs_df is not None:
            _expr_a = recon_a.payload.get("expression", {}) or {}
            _expr_b = recon_b.payload.get("expression", {}) or {}

            matches_a = find_calibration_match(
                self.calib_df,
                target_yaw=float(recon_a.angles_deg[1]),
                target_pitch=float(recon_a.angles_deg[0]),
                target_quality=float(recon_a.payload.get("quality_overall", 0.7)),
                target_expr_mouth=float(_expr_a.get("mouth_open_intensity", 0.0)),
                target_expr_smile=float(_expr_a.get("smile_intensity", 0.0)),
                bucket=view_group_a, k=5,
            )
            matches_b = find_calibration_match(
                self.calib_df,
                target_yaw=float(recon_b.angles_deg[1]),
                target_pitch=float(recon_b.angles_deg[0]),
                target_quality=float(recon_b.payload.get("quality_overall", 0.7)),
                target_expr_mouth=float(_expr_b.get("mouth_open_intensity", 0.0)),
                target_expr_smile=float(_expr_b.get("smile_intensity", 0.0)),
                bucket=view_group_a, k=5,
            )

            # Объединяем имена ближайших и смотрим их пары в calib_pairs_df
            near_names = set(matches_a["filename"]) | set(matches_b["filename"])
            local_pairs = self.calib_pairs_df[
                self.calib_pairs_df["photo_a"].isin(near_names) |
                self.calib_pairs_df["photo_b"].isin(near_names)
            ]

            # Строим локальную noise model: median per zone из этих пар
            local_noise: Dict[str, float] = {}
            for zone in MACRO_BONE_INDICES:
                col = f"zone_{zone}_error"
                if col in local_pairs.columns and len(local_pairs) > 0:
                    local_noise[zone] = float(local_pairs[col].median())

            # Передаём в decompose вместо глобальной модели
            zone_errors_dict = {z.name: z.raw_error for z in zones if z.raw_error is not None}
            calib_result = self.calibration.decompose_with_local_noise(
                zone_errors=zone_errors_dict,
                pose_delta=pose_delta,
                local_noise=local_noise,
            )
            # Переопределяем геометрические свидетельства на локальные калиброванные
            geometry_evidence["geometry_signal"] = float(np.mean([d["signal"] for d in calib_result.zone_details]))
            geometry_evidence["geometry_noise"] = float(np.mean([d["predicted_noise"] for d in calib_result.zone_details]))
            geometry_evidence["geometry_snr"] = float(calib_result.snr)
            geometry_evidence["geometry_evidence_mode"] = "local_calib"

        diagnostics = {
            "pose_delta": pose_delta,
            "face_scale_a": scale_a,
            "face_scale_b": scale_b,
            "ipd_used": landmarks_available,
            "ipd_yaw_a": float(recon_a.angles_deg[1]),
            "ipd_yaw_b": float(recon_b.angles_deg[1]),
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


def geodesic_pose_distance(R_a: np.ndarray, R_b: np.ndarray) -> float:
    """
    Вычисляет истинное геодезическое расстояние между двумя матрицами вращения в пространстве SO(3).
    Заменяет математически ошибочную Евклидову норму углов Эйлера.
    
    Формула: theta = arccos( (Trace(R_a^T * R_b) - 1) / 2 )
    """
    # Матрица относительного вращения
    R_diff = R_a.T @ R_b
    
    # След матрицы (Trace)
    trace = np.trace(R_diff)
    
    # Защита от ошибок плавающей точки (ограничение домена arccos [-1, 1])
    cos_theta = np.clip((trace - 1.0) / 2.0, -1.0, 1.0)
    
    angle_rad = np.arccos(cos_theta)
    angle_deg = np.degrees(angle_rad)
    
    return float(angle_deg)
