from __future__ import annotations

import numpy as np
from .types import ReconstructionResult, VisibilityResult
from core.constants import Z_TOLERANCE_RATIO

def compute_software_zbuffer_mask(vertices_camera: np.ndarray, resolution: int = 256) -> np.ndarray:
    """
    [CORE-03] Software Z-buffer for occlusion detection.
    [ITER-1.4] Unified tolerance (0.005) for higher forensic precision.
    """
    if vertices_camera.ndim != 2 or vertices_camera.shape[1] != 3:
        return np.zeros((vertices_camera.shape[0],), dtype=bool)

    finite_mask = np.isfinite(vertices_camera).all(axis=1)
    if not np.any(finite_mask):
        return np.zeros((vertices_camera.shape[0],), dtype=bool)

    valid_vertices = vertices_camera[finite_mask]
    x, y, z = valid_vertices[:, 0], valid_vertices[:, 1], valid_vertices[:, 2]

    x_span = max(float(x.max() - x.min()), 1e-6)
    y_span = max(float(y.max() - y.min()), 1e-6)

    x_idx = np.clip(((x - x.min()) / x_span) * (resolution - 1), 0, resolution - 1).astype(np.int32)
    y_idx = np.clip(((y - y.min()) / y_span) * (resolution - 1), 0, resolution - 1).astype(np.int32)

    z_buffer = np.full((resolution, resolution), np.inf, dtype=np.float32)
    np.minimum.at(z_buffer, (y_idx, x_idx), z)

    # [ITER-1.4] Unified tolerance
    z_min, z_max = float(z.min()), float(z.max())
    epsilon = max((z_max - z_min) * Z_TOLERANCE_RATIO, 1e-6)
    
    visible_valid = z <= (z_buffer[y_idx, x_idx] + epsilon)

    visible_mask = np.zeros((vertices_camera.shape[0],), dtype=bool)
    visible_mask[finite_mask] = visible_valid
    return visible_mask

def compute_visibility(reconstruction: ReconstructionResult, angle_threshold_deg: float) -> VisibilityResult:
    """
    Combines normal-based facing check and Z-buffer occlusion check.
    """
    # Normals camera-space (simplified normalization for example)
    normals = reconstruction.normals_camera
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / (norms + 1e-8)
    
    view_direction = np.array([0, 0, 1], dtype=np.float32)
    facing_cosines = np.sum(normals * view_direction, axis=1)
    
    cosine_threshold = float(np.cos(np.deg2rad(angle_threshold_deg)))
    binary_mask = facing_cosines >= cosine_threshold
    
    # Occlusion check
    zbuffer_mask = compute_software_zbuffer_mask(reconstruction.vertices_camera)
    binary_mask &= zbuffer_mask
    
    # Optional: combine with renderer-provided mask
    if hasattr(reconstruction, "visible_idx_renderer"):
        binary_mask &= np.asarray(reconstruction.visible_idx_renderer, dtype=bool)

    cosine_weights = np.clip((facing_cosines - cosine_threshold) / max(1e-6, 1.0 - cosine_threshold), 0.0, 1.0)
    cosine_weights *= binary_mask.astype(np.float32)

    return VisibilityResult(
        binary_mask=binary_mask,
        cosine_weights=cosine_weights,
        facing_cosines=facing_cosines,
        visible_count=int(np.count_nonzero(binary_mask)),
    )
