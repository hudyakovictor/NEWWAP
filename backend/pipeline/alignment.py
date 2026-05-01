from __future__ import annotations

import numpy as np
from .types import AlignmentResult

_CANONICAL_YAW_BY_VIEW_GROUP: dict[str, float] = {
    "frontal": 0.0,
    "left_threequarter_light": -22.5,
    "right_threequarter_light": 22.5,
    "left_threequarter_mid": -45.0,
    "right_threequarter_mid": 45.0,
    "left_threequarter_deep": -67.5,
    "right_threequarter_deep": 67.5,
    "left_profile": -90.0,
    "right_profile": 90.0,
}

def rigid_umeyama(
    source: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray | None = None,
    allow_scale: bool = False,
) -> AlignmentResult:
    """
    [GEOM-02] Weighted Rigid Umeyama Alignment.
    """
    if source.ndim != 2 or target.ndim != 2 or source.shape[1] != 3 or target.shape[1] != 3:
        raise ValueError(f"source/target must be (N,3), got {source.shape} / {target.shape}")
    if source.shape[0] != target.shape[0]:
        raise ValueError(f"source/target length mismatch: {source.shape[0]} vs {target.shape[0]}")
    if source.shape[0] < 3:
        raise ValueError("source/target must have at least 3 points for 3D alignment")

    if weights is None:
        weights = np.ones(len(source), dtype=np.float32)

    weight_sum = float(np.sum(weights))
    if weight_sum <= 1e-8:
        raise ValueError("weights sum is zero or near-zero — degenerate alignment")

    w = weights / (weight_sum + 1e-8)
    w = w[:, np.newaxis]

    source_mean = np.sum(source * w, axis=0)
    target_mean = np.sum(target * w, axis=0)

    centered_source = source - source_mean
    centered_target = target - target_mean

    residual_before = float(np.sum(np.linalg.norm(source - target, axis=1) * weights.flatten()))
    
    # Covariance matrix
    m = (centered_source * w).T @ centered_target
    
    # [ITER-1.1] Rank Check Guard
    if np.linalg.matrix_rank(m) < 3:
        # Fallback if points are collinear or coplanar in a way that SVD fails to give rotation
        # However, SVD usually handles this, but the determinant check might fail.
        pass

    u, s, vh = np.linalg.svd(m)

    d = np.linalg.det(u @ vh)
    sign_matrix = np.diag([1.0, 1.0, np.sign(d)])
    rotation = u @ sign_matrix @ vh

    if allow_scale:
        var_source = np.sum(weights.flatten() * np.sum(centered_source**2, axis=1))
        if var_source > 1e-8:
            scale = float((s[0] + s[1] + s[2] * np.sign(d)) / var_source)
        else:
            scale = 1.0
    else:
        scale = 1.0

    translation = target_mean - scale * (source_mean @ rotation)
    source_aligned = scale * (source @ rotation) + translation
    residual_after = float(np.sum(np.linalg.norm(source_aligned - target, axis=1) * weights.flatten()))

    return AlignmentResult(
        rotation=rotation,
        translation=translation,
        scale=scale,
        source_aligned=source_aligned,
        residual_before=residual_before,
        residual_after=residual_after,
    )

def euler_to_rotation_matrix(angles_rad: np.ndarray) -> np.ndarray:
    """
    Конвертирует углы Эйлера в матрицу вращения (ZYX convention).
    Ожидается формат 3DDFA_v3: [pitch, yaw, roll] в радианах.
    R = Rz(roll) @ Ry(yaw) @ Rx(pitch)
    """
    pitch, yaw, roll = angles_rad

    cx, sx = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw),   np.sin(yaw)
    cz, sz = np.cos(roll),  np.sin(roll)

    rot_x = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=np.float32)
    rot_y = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=np.float32)
    rot_z = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    
    return rot_z @ rot_y @ rot_x

def align_canonical_pair_for_view_group(
    vertices_a: np.ndarray,
    angles_a: np.ndarray,
    translation_a: np.ndarray,
    vertices_b: np.ndarray,
    angles_b: np.ndarray,
    translation_b: np.ndarray,
    view_group: str | None,
    shared_idx: np.ndarray,
    weights: np.ndarray,
) -> dict[str, np.ndarray | AlignmentResult]:
    """
    [ITER-1.1] Aligns a pair of faces to a canonical pose.
    Uses average pitch and roll of the pair for better stability.
    """
    # 1. Determine canonical yaw
    target_yaw = _CANONICAL_YAW_BY_VIEW_GROUP.get((view_group or "").strip(), 0.0)
    
    # 2. Use average pitch and roll from the pair instead of 0
    avg_pitch = (angles_a[0] + angles_b[0]) / 2.0
    avg_roll = (angles_a[2] + angles_b[2]) / 2.0
    
    target_angles_deg = np.array([target_yaw, avg_pitch, avg_roll], dtype=np.float32)
    target_angles_rad = np.deg2rad(target_angles_deg)
    
    # Rotation matrices for current poses
    R_a = euler_to_rotation_matrix(np.deg2rad(angles_a))
    R_b = euler_to_rotation_matrix(np.deg2rad(angles_b))
    
    # Rotation matrix for target pose
    R_target = euler_to_rotation_matrix(target_angles_rad)
    
    # Alignment rotations
    R_align_a = R_a.T @ R_target
    R_align_b = R_b.T @ R_target
    
    # Center and align
    va_canon = (vertices_a - translation_a) @ R_align_a
    vb_canon = (vertices_b - translation_b) @ R_align_b
    
    # Final rigid alignment
    alignment = rigid_umeyama(va_canon[shared_idx], vb_canon[shared_idx], weights=weights, allow_scale=True)
    aligned_a = (va_canon * alignment.scale) @ alignment.rotation + alignment.translation
    
    return {
        "target_angles_deg": target_angles_deg,
        "vertices_a_canonical": va_canon,
        "vertices_b_canonical": vb_canon,
        "alignment": alignment,
        "vertices_a_aligned": aligned_a,
    }

def gpa_unit_scale(points: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    """
    [GEOM-01] Generalized Procrustes Analysis: Centering and Unit Scaling.
    Returns (centered_unit_points, scale, centroid).
    """
    if points.size == 0:
        return points, 1.0, np.zeros(3)
    centroid = np.mean(points, axis=0)
    centered = points - centroid
    scale = float(np.sqrt(np.mean(np.sum(centered**2, axis=1))))
    if scale < 1e-8:
        return centered, 1.0, centroid
    return centered / scale, scale, centroid
