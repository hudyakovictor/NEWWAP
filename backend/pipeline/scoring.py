from __future__ import annotations

import numpy as np
from .alignment import rigid_umeyama
from .utils import bounded_score_from_error, weighted_mean_abs
from core.constants import TRIMMED_KEEP_RATIO, MIN_KEEP_N, FACE_SCALE_Y_FACTOR

def _get_face_scale_from_points(points: np.ndarray) -> float:
    """
    [ITER-1.2] Stable face scale estimation.
    Uses max(x_extent, y_extent * FACE_SCALE_Y_FACTOR) to avoid over-scaling in profiles.
    """
    if points.shape[0] == 0:
        return 1.0
    
    # Use percentiles to avoid outliers
    q_x = np.percentile(points[:, 0], [95, 5])
    q_y = np.percentile(points[:, 1], [95, 5])
    
    x_extent = q_x[0] - q_x[1]
    y_extent = q_y[0] - q_y[1]
    
    scale = float(max(x_extent, y_extent * FACE_SCALE_Y_FACTOR))
    return max(scale, 1e-6)

def _robust_trimmed_3d_error(
    values: np.ndarray, 
    weights: np.ndarray, 
    keep_ratio: float = TRIMMED_KEEP_RATIO,
    min_keep_n: int = MIN_KEEP_N
) -> float:
    """
    [ITER-1.2] Trimmed weighted mean with min_keep_n guard.
    """
    if values.size == 0:
        return 0.0
    
    magnitudes = np.abs(values)
    n = magnitudes.size
    
    if n <= min_keep_n:
        return weighted_mean_abs(values, weights)
    
    # Calculate how many to keep
    n_keep = max(int(n * keep_ratio), min_keep_n)
    
    # Get cutoff threshold
    cutoff = float(np.partition(magnitudes, n_keep - 1)[n_keep - 1])
    
    keep_mask = magnitudes <= cutoff
    if not np.any(keep_mask):
        return weighted_mean_abs(values, weights)
        
    return weighted_mean_abs(values[keep_mask], weights[keep_mask])

def fit_best_plane(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    centroid = points.mean(axis=0)
    centered = points - centroid
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    normal = vh[-1]
    return centroid, normal / (np.linalg.norm(normal) + 1e-8)

def score_aligned_pair(
    points_a: np.ndarray,
    points_b: np.ndarray,
    weights: np.ndarray,
    reliability_weight: float = 1.0,
) -> tuple[float, float, float, float, np.ndarray]:
    """
    [GEOM-03] Forensic 3D Scoring.
    Projects differences onto the face plane normal.
    """
    scale_b = _get_face_scale_from_points(points_b)
    _centroid_b, plane_normal = fit_best_plane(points_b)

    # 1. Difference vector
    diffs = points_a - points_b

    # 2. Project onto normal (relief changes)
    perpendicular_offsets = np.abs(np.sum(diffs * plane_normal, axis=1))

    # Normalize to face scale
    distances_proj = perpendicular_offsets / scale_b

    # Apply reliability weight (from texture/pose)
    effective_weights = weights * reliability_weight

    # Weighted mean
    primary_error = weighted_mean_abs(distances_proj, effective_weights)

    # Robust variant (trimmed)
    robust_error = _robust_trimmed_3d_error(distances_proj, effective_weights)

    return (
        primary_error,
        bounded_score_from_error(primary_error),
        robust_error,
        bounded_score_from_error(robust_error),
        plane_normal,
    )

def align_and_score(
    points_a: np.ndarray,
    points_b: np.ndarray,
    weights: np.ndarray,
    alignment_weights: np.ndarray | None = None,
    reliability_weight: float = 1.0,
) -> tuple[AlignmentResult, float, float, float, float, np.ndarray]:
    """
    Full alignment and scoring pipeline.
    """
    # [AXIOM-02] Scale must be locked (False) for forensic comparison
    alignment = rigid_umeyama(points_a, points_b, weights=alignment_weights, allow_scale=False)
    
    (
        primary_error,
        bounded_primary,
        robust_error,
        bounded_robust,
        plane_normal,
    ) = score_aligned_pair(
        alignment.source_aligned, 
        points_b, 
        weights, 
        reliability_weight=reliability_weight
    )
    
    return (
        alignment,
        primary_error,
        bounded_primary,
        robust_error,
        bounded_robust,
        plane_normal,
    )

def extract_macro_bone_metrics(
    vertices: np.ndarray, 
    bone_indices: dict[str, list[int]],
    angles: np.ndarray
) -> tuple[dict[str, float], float]:
    """
    [GEOM-01] Extraction of stable forensic features.
    """
    def get_zone_centroid(name: str) -> np.ndarray:
        idx = bone_indices.get(name, [])
        if not idx:
            return np.zeros(3)
        return np.mean(vertices[idx], axis=0)

    # 1. Base normalization by cheekbones
    cheek_L = get_zone_centroid('cheekbone_L')
    cheek_R = get_zone_centroid('cheekbone_R')
    zygomatic_breadth = float(np.linalg.norm(cheek_L - cheek_R)) or 1.0
    
    # 2. Face Height
    forehead_indices = bone_indices.get('forehead', [])
    chin_indices = bone_indices.get('chin', [])
    if not forehead_indices or not chin_indices:
        return {}, 0.0
        
    forehead_top = np.max(vertices[forehead_indices], axis=0)
    chin_bottom = np.min(vertices[chin_indices], axis=0)
    face_height = float(np.linalg.norm(forehead_top - chin_bottom)) or 1.0
    
    # 3. Indices
    metrics = {
        "cranial_face_index": zygomatic_breadth / face_height,
        "jaw_width_ratio": float(np.linalg.norm(get_zone_centroid('jaw_L') - get_zone_centroid('jaw_R'))) / zygomatic_breadth,
    }
    
    # 4. Orbital Complex
    orbit_L_pts = vertices[bone_indices.get('orbit_L', [])]
    orbit_R_pts = vertices[bone_indices.get('orbit_R', [])]
    
    def calc_tilt(p1, p2):
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        import math
        return math.degrees(math.atan2(dy, abs(dx)))

    canthus_L_inner = vertices[bone_indices.get('canthus_L_inner', [0])[0]]
    canthus_L_outer = vertices[bone_indices.get('canthus_L_outer', [0])[0]]
    canthus_R_inner = vertices[bone_indices.get('canthus_R_inner', [0])[0]]
    canthus_R_outer = vertices[bone_indices.get('canthus_R_outer', [0])[0]]

    metrics["canthal_tilt_L"] = calc_tilt(canthus_L_inner, canthus_L_outer)
    metrics["canthal_tilt_R"] = calc_tilt(canthus_R_inner, canthus_R_outer)
    
    # Orbit depth
    orbit_L_centroid = np.mean(orbit_L_pts, axis=0)
    orbit_R_centroid = np.mean(orbit_R_pts, axis=0)
    cheek_L = get_zone_centroid('cheekbone_L')
    cheek_R = get_zone_centroid('cheekbone_R')
    mid_cheek_z = (cheek_L[2] + cheek_R[2]) / 2.0
    metrics["orbit_depth_L_ratio"] = abs(orbit_L_centroid[2] - mid_cheek_z) / zygomatic_breadth
    metrics["orbit_depth_R_ratio"] = abs(orbit_R_centroid[2] - mid_cheek_z) / zygomatic_breadth
    
    # 5. Jaw/Gonial Angle
    jaw_L_pts = vertices[bone_indices.get('jaw_L', [])]
    jaw_R_pts = vertices[bone_indices.get('jaw_R', [])]
    gonion_L = jaw_L_pts[np.argmin(jaw_L_pts[:, 1])] if jaw_L_pts.size > 0 else np.zeros(3)
    gonion_R = jaw_R_pts[np.argmin(jaw_R_pts[:, 1])] if jaw_R_pts.size > 0 else np.zeros(3)
    
    metrics["gonial_angle_L"] = calc_tilt(chin_bottom, gonion_L)
    metrics["gonial_angle_R"] = calc_tilt(chin_bottom, gonion_R)

    # 6. Nose
    nose_bridge = get_zone_centroid('nose_bridge_tip')
    nose_wing_L = get_zone_centroid('nose_wing_L')
    nose_wing_R = get_zone_centroid('nose_wing_R')
    
    metrics["nose_width_ratio"] = float(np.linalg.norm(nose_wing_L - nose_wing_R)) / zygomatic_breadth
    metrics["nose_projection_ratio"] = abs(nose_bridge[2] - mid_cheek_z) / zygomatic_breadth
    
    forehead_centroid = get_zone_centroid('forehead')
    metrics["nasal_frontal_index"] = abs(forehead_centroid[2] - nose_bridge[2]) / face_height
    
    # 7. Chin
    chin_pts = vertices[bone_indices.get('chin', [])]
    chin_centroid = np.mean(chin_pts, axis=0)
    metrics["chin_projection_ratio"] = abs(chin_centroid[2] - mid_cheek_z) / zygomatic_breadth
    
    # 8. Reliability
    yaw_abs = abs(angles[1])
    pitch_abs = abs(angles[0])
    
    reliability = 1.0
    if yaw_abs > 30: reliability *= 0.5
    if pitch_abs > 20: reliability *= 0.7
    
    return metrics, reliability
