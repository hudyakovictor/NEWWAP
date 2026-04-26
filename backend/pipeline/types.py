from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass
class ReconstructionResult:
    image_path: Path
    vertices_world: np.ndarray
    vertices_camera: np.ndarray
    vertices_image: np.ndarray
    triangles: np.ndarray
    point_buffer: np.ndarray
    annotation_groups: List[np.ndarray]
    visible_idx_renderer: np.ndarray
    normals_world: np.ndarray
    normals_camera: np.ndarray
    rotation_matrix: np.ndarray
    translation: np.ndarray
    angles_deg: np.ndarray
    trans_params: Optional[np.ndarray] = None
    landmarks_106: Optional[np.ndarray] = None
    uv_coords: Optional[np.ndarray] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def points(self) -> np.ndarray:
        """Alias for vertices_world."""
        return self.vertices_world

@dataclass(frozen=True)
class VisibilityResult:
    binary_mask: np.ndarray
    cosine_weights: np.ndarray
    facing_cosines: np.ndarray
    visible_count: int

@dataclass(frozen=True)
class AlignmentResult:
    rotation: np.ndarray
    translation: np.ndarray
    scale: float
    source_aligned: np.ndarray
    residual_before: float
    residual_after: float

@dataclass(frozen=True)
class ZoneMetric:
    name: str
    status: str
    shared_vertex_count: int
    analysis_role: str
    bone_priority_class: str
    bone_weight: float
    raw_error: Optional[float] = None
    bounded_score: Optional[float] = None
    mean_weight: Optional[float] = None
    mean_signed_depth_delta: Optional[float] = None
    mean_signed_lateral_delta: Optional[float] = None
    mean_signed_vertical_delta: Optional[float] = None
    principal_shift_axis: Optional[str] = None
    dominant_shift_direction: Optional[str] = None
    delta_mm: Optional[float] = None
    delta_rel: Optional[float] = None

@dataclass(frozen=True)
class ComparisonResult:
    status: str
    shared_vertex_indices: np.ndarray
    score_raw: Optional[float]
    score_bounded: Optional[float]
    robust_score_raw: Optional[float]
    robust_score_bounded: Optional[float]
    provisional_band: str
    robust_provisional_band: str
    visibility_a: VisibilityResult
    visibility_b: VisibilityResult
    alignment: Optional[AlignmentResult]
    zones: List[ZoneMetric]
    diagnostics: Dict[str, Any] = field(default_factory=dict)
