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

    [ITER-1] ИСПРАВЛЕНИЕ: Вычисляем истинное евклидово расстояние между точками,
    а не их проекцию на одну из плоскостей. Это избегает двойного смещения
    при непараллельных плоскостях из-за погрешности детекции позы.
    """
    scale_b = _get_face_scale_from_points(points_b)
    _centroid_b, plane_normal = fit_best_plane(points_b)

    # 1. Difference vector
    diffs = points_a - points_b

    # [ITER-1] ИСПРАВЛЕНИЕ: Честное L2 расстояние между выровненными вершинами
    # Вычисляем норму по оси X,Y,Z для каждой точки
    true_distances = np.linalg.norm(diffs, axis=1)

    # Normalize to face scale
    distances_normalized = true_distances / scale_b

    # Apply reliability weight (from texture/pose)
    effective_weights = weights * reliability_weight

    # Weighted mean
    primary_error = weighted_mean_abs(distances_normalized, effective_weights)

    # Robust variant (trimmed)
    robust_error = _robust_trimmed_3d_error(distances_normalized, effective_weights)

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
        idx_raw = bone_indices.get(name, [])
        if not idx_raw:
            return np.zeros(3)
        idx = np.asarray(list(idx_raw), dtype=np.int64)
        idx = idx[(idx >= 0) & (idx < vertices.shape[0])]
        if idx.size == 0:
            return np.zeros(3)
        return np.mean(vertices[idx], axis=0)

    def _idx(name: str) -> np.ndarray:
        """Convert bone_indices entry (frozenset/list) to valid numpy index array."""
        raw = bone_indices.get(name, [])
        if not raw:
            return np.array([], dtype=np.int64)
        arr = np.asarray(list(raw), dtype=np.int64)
        return arr[(arr >= 0) & (arr < vertices.shape[0])]

    # 1. Base normalization by cheekbones
    cheek_L = get_zone_centroid('cheekbone_L')
    # cheekbone_R not in MACRO_BONE_INDICES — approximate via brow_ridge_R centroid
    cheek_R = get_zone_centroid('cheekbone_R')
    if np.allclose(cheek_R, 0):
        # Symmetric approximation: mirror cheek_L across midline
        brow_R = get_zone_centroid('brow_ridge_R')
        brow_L = get_zone_centroid('brow_ridge_L')
        if not np.allclose(brow_L, 0) and not np.allclose(brow_R, 0):
            mid_x = (brow_L[0] + brow_R[0]) / 2.0
            cheek_R = np.array([2.0 * mid_x - cheek_L[0], cheek_L[1], cheek_L[2]])
        else:
            cheek_R = cheek_L  # fallback: assume symmetric
    zygomatic_breadth = float(np.linalg.norm(cheek_L - cheek_R)) or 1.0
    mid_cheek_z = float((cheek_L[2] + cheek_R[2]) / 2.0)
    
    # 2. Face Height
    forehead_idx = _idx('forehead')
    # chin not available in MACRO_BONE_INDICES — use jaw_angle as proxy
    chin_proxy_idx = _idx('jaw_angle_L')
    if chin_proxy_idx.size == 0:
        chin_proxy_idx = _idx('jaw_angle_R')
    if forehead_idx.size == 0 or chin_proxy_idx.size == 0:
        return {}, 0.0
        
    forehead_top = np.max(vertices[forehead_idx], axis=0)
    chin_bottom = np.min(vertices[chin_proxy_idx], axis=0)
    face_height = float(np.linalg.norm(forehead_top - chin_bottom)) or 1.0
    
    # 3. Indices
    metrics = {
        "cranial_face_index": zygomatic_breadth / face_height,
        "jaw_width_ratio": float(np.linalg.norm(get_zone_centroid('jaw_angle_L') - get_zone_centroid('jaw_angle_R'))) / zygomatic_breadth,
    }
    
    # 4. Orbital Complex
    orbit_L_idx = _idx('orbit_L')
    orbit_R_idx = _idx('orbit_R')
    orbit_L_pts = vertices[orbit_L_idx] if orbit_L_idx.size > 0 else np.zeros((0, 3))
    orbit_R_pts = vertices[orbit_R_idx] if orbit_R_idx.size > 0 else np.zeros((0, 3))
    
    def calc_tilt(p1, p2):
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        import math
        return math.degrees(math.atan2(dy, abs(dx)))

    # Canthal tilt: use orbit bounding box edges as proxy when canthus landmarks are absent
    canthus_L_inner_idx = _idx('canthus_L_inner')
    canthus_L_outer_idx = _idx('canthus_L_outer')
    canthus_R_inner_idx = _idx('canthus_R_inner')
    canthus_R_outer_idx = _idx('canthus_R_outer')
    
    if canthus_L_inner_idx.size > 0 and canthus_L_outer_idx.size > 0:
        canthus_L_inner = vertices[canthus_L_inner_idx[0]]
        canthus_L_outer = vertices[canthus_L_outer_idx[0]]
    elif orbit_L_pts.size > 0:
        # Fallback: use orbit bounding box edges as canthus proxy
        canthus_L_inner = orbit_L_pts[np.argmin(orbit_L_pts[:, 0])]  # medial
        canthus_L_outer = orbit_L_pts[np.argmax(orbit_L_pts[:, 0])]  # lateral
    else:
        canthus_L_inner = canthus_L_outer = np.zeros(3)
    
    if canthus_R_inner_idx.size > 0 and canthus_R_outer_idx.size > 0:
        canthus_R_inner = vertices[canthus_R_inner_idx[0]]
        canthus_R_outer = vertices[canthus_R_outer_idx[0]]
    elif orbit_R_pts.size > 0:
        canthus_R_inner = orbit_R_pts[np.argmax(orbit_R_pts[:, 0])]  # medial (right side)
        canthus_R_outer = orbit_R_pts[np.argmin(orbit_R_pts[:, 0])]  # lateral
    else:
        canthus_R_inner = canthus_R_outer = np.zeros(3)

    metrics["canthal_tilt_L"] = calc_tilt(canthus_L_inner, canthus_L_outer)
    metrics["canthal_tilt_R"] = calc_tilt(canthus_R_inner, canthus_R_outer)
    
    # Orbit depth (NaN guard)
    if orbit_L_pts.size > 0:
        orbit_L_centroid = np.mean(orbit_L_pts, axis=0)
        metrics["orbit_depth_L_ratio"] = abs(orbit_L_centroid[2] - mid_cheek_z) / zygomatic_breadth
    if orbit_R_pts.size > 0:
        orbit_R_centroid = np.mean(orbit_R_pts, axis=0)
        metrics["orbit_depth_R_ratio"] = abs(orbit_R_centroid[2] - mid_cheek_z) / zygomatic_breadth
    
    # 5. Jaw/Gonial Angle — use jaw_angle_L/R (point landmarks)
    jaw_L_idx = _idx('jaw_angle_L')
    jaw_R_idx = _idx('jaw_angle_R')
    jaw_L_pts = vertices[jaw_L_idx] if jaw_L_idx.size > 0 else np.zeros((0, 3))
    jaw_R_pts = vertices[jaw_R_idx] if jaw_R_idx.size > 0 else np.zeros((0, 3))
    
    if jaw_L_pts.size > 0 and jaw_R_pts.size > 0:
        gonion_L = jaw_L_pts[np.argmin(jaw_L_pts[:, 1])]
        gonion_R = jaw_R_pts[np.argmin(jaw_R_pts[:, 1])]
        metrics["gonial_angle_L"] = calc_tilt(chin_bottom, gonion_L)
        metrics["gonial_angle_R"] = calc_tilt(chin_bottom, gonion_R)
    elif jaw_R_pts.size > 0:
        # Fallback: if only right side available, use symmetric assumption
        gonion_R = jaw_R_pts[np.argmin(jaw_R_pts[:, 1])]
        angle_R = calc_tilt(chin_bottom, gonion_R)
        metrics["gonial_angle_R"] = angle_R
        metrics["gonial_angle_L"] = angle_R  # Symmetric fallback
    elif jaw_L_pts.size > 0:
        # Fallback: if only left side available, use symmetric assumption
        gonion_L = jaw_L_pts[np.argmin(jaw_L_pts[:, 1])]
        angle_L = calc_tilt(chin_bottom, gonion_L)
        metrics["gonial_angle_L"] = angle_L
        metrics["gonial_angle_R"] = angle_L  # Symmetric fallback
    else:
        # No jaw angle landmarks available
        metrics["gonial_angle_L"] = 0.0
        metrics["gonial_angle_R"] = 0.0

    # 6. Nose
    nose_bridge = get_zone_centroid('nose_bridge_tip')
    nose_wing_L = get_zone_centroid('nose_wing_L')
    nose_wing_R = get_zone_centroid('nose_wing_R')
    
    metrics["nose_width_ratio"] = float(np.linalg.norm(nose_wing_L - nose_wing_R)) / zygomatic_breadth
    metrics["nose_projection_ratio"] = abs(nose_bridge[2] - mid_cheek_z) / zygomatic_breadth
    
    forehead_centroid = get_zone_centroid('forehead')
    metrics["nasal_frontal_index"] = abs(forehead_centroid[2] - nose_bridge[2]) / face_height
    
    # 7. Chin — use jaw_angle average as chin proxy (chin zone not in MACRO_BONE_INDICES)
    chin_pts = vertices[np.concatenate([_idx('jaw_angle_L'), _idx('jaw_angle_R')])]
    chin_centroid = np.mean(chin_pts, axis=0) if chin_pts.size > 0 else chin_bottom
    metrics["chin_projection_ratio"] = abs(chin_centroid[2] - mid_cheek_z) / zygomatic_breadth
    
    # 8. Interorbital ratio
    orbit_L_c = get_zone_centroid('orbit_L')
    orbit_R_c = get_zone_centroid('orbit_R')
    metrics["interorbital_ratio"] = float(np.linalg.norm(orbit_L_c - orbit_R_c)) / zygomatic_breadth

    # 9. Forehead slope index (forehead tilt relative to face plane)
    forehead_c = get_zone_centroid('forehead')
    nose_bridge_c = get_zone_centroid('nose_bridge_tip')
    fh_slope_z = abs(forehead_c[2] - nose_bridge_c[2])
    metrics["forehead_slope_index"] = fh_slope_z / face_height

    # 10. Nasofacial angle ratio (nose protrusion vs face height)
    nose_protrusion = abs(nose_bridge_c[2] - mid_cheek_z)
    metrics["nasofacial_angle_ratio"] = nose_protrusion / face_height

    # 11. Orbital asymmetry index (L vs R orbit depth difference)
    od_L = metrics.get("orbit_depth_L_ratio", 0.0)
    od_R = metrics.get("orbit_depth_R_ratio", 0.0)
    metrics["orbital_asymmetry_index"] = abs(od_L - od_R)

    # 12. Chin offset asymmetry (chin lateral offset from midline)
    if chin_pts.size > 0:
        midline_x = (cheek_L[0] + cheek_R[0]) / 2.0
        metrics["chin_offset_asymmetry"] = abs(chin_centroid[0] - midline_x) / zygomatic_breadth
    else:
        metrics["chin_offset_asymmetry"] = 0.0

    # 13. Reliability
    yaw_abs = abs(angles[1])
    pitch_abs = abs(angles[0])
    
    reliability = 1.0
    if yaw_abs > 30: reliability *= 0.5
    if pitch_abs > 20: reliability *= 0.7
    
    return metrics, reliability
