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

def compute_interorbital_ratio(canthus_L_inner: np.ndarray, canthus_R_inner: np.ndarray, zygomatic_breadth: float) -> float:
    """
    [K-03] Вычисляет отношение межорбитального расстояния к скуловой ширине.
    """
    if np.allclose(canthus_L_inner, 0) or np.allclose(canthus_R_inner, 0) or zygomatic_breadth <= 1e-6:
        return 0.0
    interorbital_dist = float(np.linalg.norm(canthus_L_inner - canthus_R_inner))
    return interorbital_dist / zygomatic_breadth

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

def calc_3d_angle(v1, vertex, v2):
    """Вычисляет истинный 3D-угол между тремя точками"""
    a = np.array(v1) - np.array(vertex)
    b = np.array(v2) - np.array(vertex)
    
    # Защита от деления на ноль
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
        
    cos_a = np.dot(a, b) / (norm_a * norm_b)
    # Защита от выхода за пределы [-1, 1] из-за погрешностей float
    return float(np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0))))


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
    chin_idx = _idx('chin')
    if chin_idx.size == 0:
        chin_idx = _idx('jaw_angle_L')
    if chin_idx.size == 0:
        chin_idx = _idx('jaw_angle_R')
    if forehead_idx.size == 0 or chin_idx.size == 0:
        return {}, 0.0
        
    forehead_top = np.max(vertices[forehead_idx], axis=0)
    chin_bottom = np.min(vertices[chin_idx], axis=0)
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
    
    def calc_tilt_3d_coronal(p_inner, p_outer, face_normal, side='L'):
        """
        Вычисляет наклон глазной щели строго в корональной плоскости лица.
        Устойчиво к yaw-вращениям до 70 градусов.
        """
        import math
        # Вектор от внутреннего угла к внешнему
        eye_vector = p_outer - p_inner

        # Для правого глаза инвертируем направление вектора,
        # чтобы угол измерялся в одной системе координат с левым
        if side == 'R':
            eye_vector = -eye_vector
        
        # Проецируем вектор на плоскость лица (удаляем Z-компоненту относительно нормали лица)
        eye_vector_proj = eye_vector - np.dot(eye_vector, face_normal) * face_normal
        
        # Нормализуем
        eye_vector_proj = eye_vector_proj / (np.linalg.norm(eye_vector_proj) + 1e-8)
        
        # Определяем горизонтальную ось лица (cross product нормали и вектора "вверх" Y=[0,-1,0])
        up_vector = np.array([0, -1, 0]) 
        face_horizontal = np.cross(face_normal, up_vector)
        face_horizontal = face_horizontal / (np.linalg.norm(face_horizontal) + 1e-8)
        
        # Считаем угол между спроецированным вектором глаза и горизонталью лица
        sin_theta = np.linalg.norm(np.cross(face_horizontal, eye_vector_proj))
        cos_theta = np.dot(face_horizontal, eye_vector_proj)
        
        return math.degrees(math.atan2(sin_theta, cos_theta))

    def calc_3d_perimeter(points_array):
        """Сумма 3D-расстояний между последовательными точками контура."""
        if points_array.size == 0:
            return 0.0
        perimeter = 0.0
        for i in range(len(points_array)):
            p1 = points_array[i]
            p2 = points_array[(i + 1) % len(points_array)] # замыкаем контур
            perimeter += np.linalg.norm(p2 - p1)
        return perimeter

    def calc_point_to_line_distance(point, line_p1, line_p2):
        """Кратчайшее 3D расстояние от точки до прямой, заданной двумя точками."""
        line_vec = line_p2 - line_p1
        point_vec = point - line_p1
        cross_prod = np.cross(line_vec, point_vec)
        return np.linalg.norm(cross_prod) / (np.linalg.norm(line_vec) + 1e-8)

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

    # 1.3 Face Plane Overhaul: Собираем только стабильные лицевые вершины для расчета строгой нормали
    face_mask_indices = np.concatenate([
        _idx('nose_bridge_tip'), _idx('orbit_L'), _idx('orbit_R'),
        _idx('cheekbone_L'), _idx('cheekbone_R'), _idx('forehead')
    ])
    if face_mask_indices.size > 0:
        face_vertices_only = vertices[face_mask_indices]
        _, face_plane_normal = fit_best_plane(face_vertices_only)
    else:
        _, face_plane_normal = fit_best_plane(vertices)

    # Гарантируем, что нормаль лица смотрит "наружу" (в сторону камеры Z+ в 3DDFA)
    if face_plane_normal[2] < 0:
        face_plane_normal = -face_plane_normal

    metrics["canthal_tilt_3d_L"] = calc_tilt_3d_coronal(canthus_L_inner, canthus_L_outer, face_plane_normal, side='L')
    metrics["canthal_tilt_3d_R"] = calc_tilt_3d_coronal(canthus_R_inner, canthus_R_outer, face_plane_normal, side='R')
    metrics["canthal_tilt_L"] = metrics["canthal_tilt_3d_L"]
    metrics["canthal_tilt_R"] = metrics["canthal_tilt_3d_R"]
    metrics["interorbital_ratio"] = compute_interorbital_ratio(canthus_L_inner, canthus_R_inner, zygomatic_breadth)
    
    def depth_along_normal(point: np.ndarray, reference: np.ndarray, normal: np.ndarray) -> float:
        """
        Сохраняем знак: положительное значение — точка выступает ВПЕРЕД от плоскости (normal).
        Отрицательное — точка утоплена ВНУТРЬ (например, орбиты).
        """
        return float(np.dot(point - reference, normal))

    mid_cheek_pt = (cheek_L + cheek_R) / 2.0

    if orbit_L_pts.size > 0:
        orbit_L_centroid = np.mean(orbit_L_pts, axis=0)
        metrics["orbit_depth_L_ratio"] = depth_along_normal(
            orbit_L_centroid, mid_cheek_pt, face_plane_normal
        ) / zygomatic_breadth
    if orbit_R_pts.size > 0:
        orbit_R_centroid = np.mean(orbit_R_pts, axis=0)
        metrics["orbit_depth_R_ratio"] = depth_along_normal(
            orbit_R_centroid, mid_cheek_pt, face_plane_normal
        ) / zygomatic_breadth
    
    # 5. Jaw/Gonial Angle — use jaw_angle_L/R (point landmarks)
    jaw_L_idx = _idx('jaw_angle_L')
    jaw_R_idx = _idx('jaw_angle_R')
    jaw_L_pts = vertices[jaw_L_idx] if jaw_L_idx.size > 0 else np.zeros((0, 3))
    jaw_R_pts = vertices[jaw_R_idx] if jaw_R_idx.size > 0 else np.zeros((0, 3))
    
    ramus_L = get_zone_centroid('jaw_L')
    ramus_R = get_zone_centroid('jaw_R')
    
    if jaw_L_pts.size > 0 and jaw_R_pts.size > 0:
        gonion_L = jaw_L_pts[np.argmax(jaw_L_pts[:, 1])]
        gonion_R = jaw_R_pts[np.argmax(jaw_R_pts[:, 1])]
        
        # If ramus centroid is not valid, fallback to gonion with an upward offset
        if np.allclose(ramus_L, 0):
            ramus_L = gonion_L + np.array([0.0, 50.0, 0.0])
        if np.allclose(ramus_R, 0):
            ramus_R = gonion_R + np.array([0.0, 50.0, 0.0])
            
        metrics["gonial_angle_L"] = calc_3d_angle(ramus_L, gonion_L, chin_bottom)
        metrics["gonial_angle_R"] = calc_3d_angle(ramus_R, gonion_R, chin_bottom)
    elif jaw_R_pts.size > 0:
        gonion_R = jaw_R_pts[np.argmax(jaw_R_pts[:, 1])]
        if np.allclose(ramus_R, 0):
            ramus_R = gonion_R + np.array([0.0, 50.0, 0.0])
        angle_R = calc_3d_angle(ramus_R, gonion_R, chin_bottom)
        metrics["gonial_angle_R"] = angle_R
        metrics["gonial_angle_L"] = angle_R  # Symmetric fallback
    elif jaw_L_pts.size > 0:
        gonion_L = jaw_L_pts[np.argmax(jaw_L_pts[:, 1])]
        if np.allclose(ramus_L, 0):
            ramus_L = gonion_L + np.array([0.0, 50.0, 0.0])
        angle_L = calc_3d_angle(ramus_L, gonion_L, chin_bottom)
        metrics["gonial_angle_L"] = angle_L
        metrics["gonial_angle_R"] = angle_L  # Symmetric fallback
    else:
        # No jaw angle landmarks available
        metrics["gonial_angle_L"] = 0.0
        metrics["gonial_angle_R"] = 0.0

    # 5b. Mandibular ramus length — боковой аналог jaw_width_ratio для профильного ракурса
    # Длина ветви от gonion до chin_bottom, нормированная на face_height
    _gonion_for_ramus = None
    if jaw_L_pts.size > 0:
        _gonion_for_ramus = jaw_L_pts[np.argmax(jaw_L_pts[:, 1])]
    elif jaw_R_pts.size > 0:
        _gonion_for_ramus = jaw_R_pts[np.argmax(jaw_R_pts[:, 1])]

    if _gonion_for_ramus is not None:
        metrics["mandibular_ramus_length"] = (
            float(np.linalg.norm(_gonion_for_ramus - chin_bottom)) / face_height
        )
    else:
        metrics["mandibular_ramus_length"] = None

    nose_bridge = get_zone_centroid('nose_bridge_tip')
    nose_wing_L = get_zone_centroid('nose_wing_L')
    nose_wing_R = get_zone_centroid('nose_wing_R')
    
    if not np.allclose(nose_wing_L, 0) and not np.allclose(nose_wing_R, 0):
        metrics["nose_width_ratio"] = float(np.linalg.norm(nose_wing_L - nose_wing_R)) / zygomatic_breadth
    else:
        metrics["nose_width_ratio"] = None
    metrics["nose_projection_ratio"] = depth_along_normal(nose_bridge, mid_cheek_pt, face_plane_normal) / zygomatic_breadth
    
    forehead_centroid = get_zone_centroid('forehead')
    metrics["nasal_frontal_index"] = depth_along_normal(forehead_centroid, nose_bridge, face_plane_normal) / face_height
    
    # 7. Chin — use jaw_angle average as chin proxy (chin zone not in MACRO_BONE_INDICES)
    chin_pts = vertices[np.concatenate([_idx('jaw_angle_L'), _idx('jaw_angle_R')])]
    chin_centroid = np.mean(chin_pts, axis=0) if chin_pts.size > 0 else chin_bottom
    metrics["chin_projection_ratio"] = depth_along_normal(chin_centroid, mid_cheek_pt, face_plane_normal) / zygomatic_breadth
    
    # 8. Orbit Centroid Ratio (to prevent overwriting step 4 interorbital_ratio)
    orbit_L_c = get_zone_centroid('orbit_L')
    orbit_R_c = get_zone_centroid('orbit_R')
    metrics["orbit_centroid_ratio"] = float(np.linalg.norm(orbit_L_c - orbit_R_c)) / zygomatic_breadth

    # 9. Forehead slope index (forehead tilt relative to brow ridge) & Glabella-Nasion angle
    forehead_c = get_zone_centroid('forehead')
    brow_L = get_zone_centroid('brow_ridge_L')
    brow_R = get_zone_centroid('brow_ridge_R')
    brow_c = (brow_L + brow_R) / 2.0
    
    glabella_pt = brow_c
    nasion_pt = get_zone_centroid('nose_bridge_tip')
    forehead_vec = glabella_pt - nasion_pt
    forehead_vec = forehead_vec / (np.linalg.norm(forehead_vec) + 1e-8)
    
    import math
    metrics["glabella_nasion_projection_angle"] = math.degrees(math.acos(
        np.clip(np.dot(forehead_vec, face_plane_normal), -1.0, 1.0)
    ))
    metrics["forehead_slope_index"] = float(metrics["glabella_nasion_projection_angle"] / 90.0)

    # 10. Nasofacial angle ratio (nose protrusion vs face height)
    nose_bridge_c = get_zone_centroid('nose_bridge_tip')
    metrics["nasofacial_angle_ratio"] = depth_along_normal(nose_bridge_c, mid_cheek_pt, face_plane_normal) / face_height

    # 11. Orbital asymmetry index & 3D Perimeter symmetry (3D perimeter ratio based)
    perimeter_L = calc_3d_perimeter(orbit_L_pts)
    perimeter_R = calc_3d_perimeter(orbit_R_pts)
    metrics["orbital_perimeter_symmetry"] = min(perimeter_L, perimeter_R) / (max(perimeter_L, perimeter_R) + 1e-8)
    metrics["orbital_asymmetry_index"] = float(1.0 - metrics["orbital_perimeter_symmetry"])

    # 12. Gnathion midline deviation
    nasion_pt = get_zone_centroid('nose_bridge_tip')
    subnasale_pt = (get_zone_centroid('nose_wing_L') + get_zone_centroid('nose_wing_R')) / 2.0
    gnathion_pt = get_zone_centroid('chin')
    if np.allclose(gnathion_pt, 0):
        gnathion_pt = chin_bottom
        
    metrics["gnathion_midline_deviation_ratio"] = calc_point_to_line_distance(
        gnathion_pt, nasion_pt, subnasale_pt
    ) / zygomatic_breadth

    # 13. Reliability
    yaw_abs = abs(angles[1])
    pitch_abs = abs(angles[0])
    
    reliability = 1.0
    if yaw_abs > 30: reliability *= 0.5
    if pitch_abs > 20: reliability *= 0.7
    
    # Pitch guard: при наклоне головы > 20° подбородок геометрически недостоверен,
    # но только для околофронтальных ракурсов (abs(yaw) <= 30.0).
    # Для выраженных профилей подбородок и профиль носа видны идеально.
    if pitch_abs > 20.0 and yaw_abs <= 30.0:
        metrics["chin_projection_ratio"] = None
        metrics["gnathion_midline_deviation_ratio"] = None

    # Mask unreliable canthal tilt & orbit depth on the occluded side for non-frontal views (yaw > 20.0)
    if yaw_abs > 20.0:
        if angles[1] < 0:  # Left profile/threequarter: right side is occluded
            metrics["canthal_tilt_R"] = None
            metrics["canthal_tilt_3d_R"] = None
            metrics["orbit_depth_R_ratio"] = None
        else:              # Right profile/threequarter: left side is occluded
            metrics["canthal_tilt_L"] = None
            metrics["canthal_tilt_3d_L"] = None
            metrics["orbit_depth_L_ratio"] = None
    
    return metrics, reliability


def apply_expression_exclusion_mask(metrics: dict, expression_params: np.ndarray) -> dict:
    """
    Удаляет зоны, искаженные мимикой. 
    Использует np.nan вместо None для безопасности матричных вычислений.
    """
    smile_intensity = expression_params[0]
    
    cleaned_metrics = metrics.copy()
    
    if smile_intensity > 2.2:
        # Улыбка искажает ширину носа и челюсть
        # ВАЖНО: Заменяем на np.nan, а не None и не 0.0
        cleaned_metrics['nose_width_ratio'] = np.nan
        cleaned_metrics['jaw_width_ratio'] = np.nan
        
    return cleaned_metrics


def calculate_coverage(cleaned_metrics: dict, pose_bucket: str) -> float:
    """
    Счет реального покрытия (Coverage).
    Если зона удалена из-за мимики (np.nan), она снижает покрытие.
    """
    from backend.core.utils import BUCKET_METRIC_KEYS
    expected_keys = BUCKET_METRIC_KEYS.get(pose_bucket, [])
    if not expected_keys:
        return 0.0
        
    valid_count = sum(
        1 for key in expected_keys 
        if key in cleaned_metrics and cleaned_metrics[key] is not None and not (isinstance(cleaned_metrics[key], float) and np.isnan(cleaned_metrics[key]))
    )
    
    return valid_count / len(expected_keys)

