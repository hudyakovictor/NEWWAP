from __future__ import annotations

import math
import threading
from pathlib import Path
import sys
from typing import Any, Dict
from pydantic import BaseModel

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from pipeline.detect_pose import PoseDetector
from pipeline.quality_gate import QualityGate
from pipeline.reconstruction import ReconstructionAdapter, ReconstructionResult, resolve_reconstruction
from pipeline.scoring import extract_macro_bone_metrics
from pipeline.texture import SkinTextureAnalyzer
from pipeline.zones import MACRO_BONE_INDICES
try:
    from uv_module.hd_uv_generator import HDUVConfig, HDUVTextureGenerator
    _UV_AVAILABLE = True
except ImportError:
    _UV_AVAILABLE = False
    HDUVConfig = None  # type: ignore
    HDUVTextureGenerator = None  # type: ignore

from .config import SETTINGS
from .constants import (
    ALIGNMENT_MIN_RANK,
    ARTIFACT_VERSION,
    MIN_ZONE_VERTICES,
)
from .utils import (
    BUCKET_METRIC_KEYS,
    RAW_BUCKET_TO_UI,
    ForensicManifest,
    ensure_directory,
    iso_now,
    read_json,
    runtime_config_snapshot,
    write_json,
)

_RUNTIME_LOCK = threading.Lock()
_RUNTIME: "LegacyRuntime | None" = None


class BayesianEvidence(BaseModel):
    h0_same_person: float
    h1_synthetic_mask: float
    h2_different_person: float
    structural_snr: float
    anomalies_flagged: int


# Веса зон по реальным ключам из BUCKET_METRIC_KEYS.
# Приоритет на неизменные костные структуры согласно ТЗ.
ZONE_WEIGHTS = {
    "nose_projection_ratio": 1.0,   # Проекция носа (переносица) — максимальный вес
    "orbit_depth_L_ratio": 1.0,     # Глубина глазниц L
    "orbit_depth_R_ratio": 1.0,     # Глубина глазниц R
    "jaw_width_ratio": 0.9,         # Ширина челюсти
    "cranial_face_index": 0.9,      # Краниальный индекс
    "canthal_tilt_L": 0.8,          # Кантальный угол L
    "canthal_tilt_R": 0.8,          # Кантальный угол R
    "texture_silicone_prob": 0.2,   # Текстурный признак силикона (мягкие ткани)
}


def calculate_bayesian_evidence(
    summary_a: Dict[str, Any],
    summary_b: Dict[str, Any],
) -> Dict[str, Any]:
    """
    [ITER-5] Advanced Forensic Bayesian Evidence Breakdown.
    Computes probabilities for H0 (Same), H1 (Synthetic), H2 (Different)
    and returns a structured breakdown for the Evidence UI.
    """
    metrics_a = summary_a.get("metrics", {})
    metrics_b = summary_b.get("metrics", {})
    tex_a = summary_a.get("texture_forensics", {})
    tex_b = summary_b.get("texture_forensics", {})
    pose_a = summary_a.get("pose", {})
    pose_b = summary_b.get("pose", {})

    # 1. Geometric Comparison
    total_weight = 0.0
    weighted_delta = 0.0
    
    # We use bone-priority zones from real BUCKET_METRIC_KEYS
    bone_zones = ["nose_projection_ratio", "orbit_depth_L_ratio", "orbit_depth_R_ratio", "jaw_width_ratio", "cranial_face_index"]
    soft_zones = ["texture_silicone_prob"]
    canthal_zones = ["canthal_tilt_L", "canthal_tilt_R"]
    
    is_smiling = pose_a.get("expression") == "smile" or pose_b.get("expression") == "smile"
    
    bone_delta_sum = 0.0
    ligament_delta_sum = 0.0
    soft_delta_sum = 0.0

    for zone, weight in ZONE_WEIGHTS.items():
        if is_smiling and zone in ["lips", "cheeks"]:
            continue
            
        val_a = metrics_a.get(zone, 0.5) # Default to 0.5 if missing
        val_b = metrics_b.get(zone, 0.5)
        delta = abs(val_a - val_b)
        
        weighted_delta += delta * weight
        total_weight += weight
        
        if zone in bone_zones:
            bone_delta_sum += delta
        elif zone in canthal_zones:
            ligament_delta_sum += delta
        elif zone in soft_zones:
            soft_delta_sum += delta

    mean_divergence = (weighted_delta / total_weight) if total_weight > 0 else 1.0
    structural_snr = max(0.1, 10.0 - mean_divergence * 20.0) # Scaled for UI

    # 2. Texture Comparison (H1 evidence)
    # If either photo shows high silicone probability, H1 likelihood increases
    silicone_a = float(tex_a.get("silicone_probability", 0.0))
    silicone_b = float(tex_b.get("silicone_probability", 0.0))
    max_silicone = max(silicone_a, silicone_b)
    
    # Complexity/Uniformity (LBP)
    lbp_a = float(tex_a.get("lbp_complexity", 0.5))
    lbp_b = float(tex_b.get("lbp_complexity", 0.5))
    
    # 3. Bayesian Logic
    priors = {"H0": 0.78, "H1": 0.02, "H2": 0.20}
    
    # Bone structures are extremely stable for the same person.
    # Ligaments are stable but affected by resolution/aging.
    # Likelihood of observing delta given H0 (Same Person)
    # Using Gaussian-like decay: exp(-delta^2 / (2 * sigma^2))
    l_h0_bone = math.exp(-(bone_delta_sum**2) / (2 * 0.04**2))
    l_h0_lig = math.exp(-(ligament_delta_sum**2) / (2 * 0.06**2))
    l_h0_geom = l_h0_bone * 0.7 + l_h0_lig * 0.3
    
    # Likelihood given H2 (Different Person) - uniform-ish over range
    l_h2_geom = 1.0 - l_h0_geom
    
    # Likelihood of observing texture given H1 (Synthetic)
    # Sigmoid on silicone probability
    l_h1_tex = 1.0 / (1.0 + math.exp(-12.0 * (max_silicone - 0.42)))
    
    # Combined evidence synthesis
    # H0 needs both geometry stability AND low synthetic probability
    ev_h0 = priors["H0"] * l_h0_geom * (1.0 - l_h1_tex)
    # H1 is driven mostly by texture but usually has good geometry (mask on face)
    # NOTE: removed arbitrary *20.0 multiplier that was breaking Bayesian normalization
    ev_h1 = priors["H1"] * l_h1_tex
    # H2 is driven by geometric divergence
    ev_h2 = priors["H2"] * l_h2_geom * (1.0 - l_h1_tex)
    
    z = ev_h0 + ev_h1 + ev_h2
    posteriors = {
        "H0": round(ev_h0 / z, 4),
        "H1": round(ev_h1 / z, 4),
        "H2": round(ev_h2 / z, 4),
    }

    # 4. Chronology Flags
    year_a = summary_a.get("year", summary_a.get("parsed_year", 2000))
    year_b = summary_b.get("year", summary_b.get("parsed_year", 2000))
    delta_years = abs(year_a - year_b)
    
    # 5. Pose Mutual Visibility
    yaw_a = abs(pose_a.get("yaw", 0.0))
    yaw_b = abs(pose_b.get("yaw", 0.0))
    # Mutual visibility is high if both are frontal
    mutual_vis = max(0.0, 1.0 - (yaw_a + yaw_b) / 180.0)

    # Final breakdown in UI-expected shape
    return {
        "aId": summary_a.get("photo_id"),
        "bId": summary_b.get("photo_id"),
        "geometric": {
            "snr": round(structural_snr, 2),
            "boneScore": round(max(0, 1.0 - bone_delta_sum), 3),
            "ligamentScore": round(max(0, 1.0 - ligament_delta_sum), 3),
            "softTissueScore": round(max(0, 1.0 - soft_delta_sum), 3),
        },
        "texture": {
            "syntheticProb": round(max_silicone, 3),
            "fft": round(float(tex_a.get("fft_high_freq_ratio", 0.5)), 3),
            "lbp": round(lbp_a, 3),
            "albedo": round(float(tex_a.get("albedo_uniformity", 0.5)), 3),
            "specular": round(float(tex_a.get("specular_gloss", 0.5)), 3),
        },
        "chronology": {
            "deltaYears": delta_years,
            "boneJump": round(bone_delta_sum, 3),
            "ligamentJump": round(ligament_delta_sum, 3),
            "flags": ["POSSIBLE_AGING"] if delta_years > 5 else [],
        },
        "pose": {
            "mutualVisibility": round(mutual_vis, 2),
            "expressionExcluded": 1 if is_smiling else 0,
        },
        "likelihoods": {"H0": round(l_h0_geom, 3), "H1": round(l_h1_tex, 3), "H2": round(l_h2_geom, 3)},
        "priors": priors,
        "posteriors": posteriors,
        "verdict": "H0" if posteriors["H0"] > 0.6 else ("H1" if posteriors["H1"] > 0.5 else "H2"),
    }




class LegacyRuntime:
    def __init__(self) -> None:
        self.pose_detector = PoseDetector(device="cpu")
        self.reconstruction = ReconstructionAdapter(device="cpu", detector_device="cpu")
        self.texture = SkinTextureAnalyzer()
        self.quality = QualityGate(
            blur_threshold=SETTINGS.blur_threshold,
            noise_threshold=SETTINGS.noise_threshold,
        )
        if _UV_AVAILABLE and HDUVConfig is not None and HDUVTextureGenerator is not None:
            self.uv = HDUVTextureGenerator(
                HDUVConfig(
                    uv_size=768,
                    super_sample=1,
                    verbose=False,
                    enable_delighting=False,
                )
            )
        else:
            self.uv = None  # UV module not available in this environment


def get_runtime() -> LegacyRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = LegacyRuntime()
        return _RUNTIME


def _zone_indices(zone_name: str) -> np.ndarray:
    return np.fromiter(MACRO_BONE_INDICES.get(zone_name, []), dtype=np.int64)


def _zone_centroid(vertices: np.ndarray, zone_name: str) -> np.ndarray:
    idx = _zone_indices(zone_name)
    if idx.size == 0:
        return np.zeros(3, dtype=np.float32)
    idx = idx[(idx >= 0) & (idx < vertices.shape[0])]
    if idx.size == 0:
        return np.zeros(3, dtype=np.float32)
    return np.mean(vertices[idx], axis=0)


def _normalize_vertices(vertices: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
    """
    [STAB-01] Робастная нормализация.
    Используем межскуловое расстояние (Zygomatic Breadth) как наиболее стабильную костную базу.
    Это исключает влияние прически, головных уборов и мимики на масштаб модели.
    """
    centered = np.asarray(vertices, dtype=np.float32) - np.mean(vertices, axis=0, keepdims=True)
    
    # Извлекаем центроиды скул для масштаба
    cheek_L = np.mean(centered[list(MACRO_BONE_INDICES['cheekbone_L'])], axis=0)
    cheek_R = np.mean(centered[list(MACRO_BONE_INDICES['cheekbone_R'])], axis=0)
    zygomatic_breadth = float(np.linalg.norm(cheek_L - cheek_R)) or 1e-6
    
    normalized = centered / zygomatic_breadth
    return normalized, {
        "stable_scale": zygomatic_breadth,
        "zygomatic_breadth": zygomatic_breadth,
    }


def _compute_geometry_metrics(recon: ReconstructionResult, bucket: str) -> tuple[dict[str, float], float]:
    metrics, reliability = extract_macro_bone_metrics(recon.vertices_world, MACRO_BONE_INDICES, recon.angles_deg)
    
    # [ITER-1] Структурные маркеры с учетом позы
    asymmetry = compute_asymmetry_vector(recon.vertices_world, bucket)
    ligaments = compute_ligament_distances(recon.vertices_world, bucket)
    
    # [ITER-2] Объемные показатели
    volumes = compute_volume_indices(recon.vertices_world, bucket)
    
    metrics.update(asymmetry)
    metrics.update(ligaments)
    metrics.update(volumes)
    
    return metrics, reliability


def compute_asymmetry_vector(vertices: np.ndarray, bucket: str) -> dict[str, float]:
    """
    [ITER-1.2] Вектор костной асимметрии.
    Рассчитывается только в фронтальном ракурсе.
    """
    if bucket != 'frontal':
        return {}
    
    # Углы челюсти
    jaw_L = _zone_centroid(vertices, 'jaw_angle_L')
    jaw_R = _zone_centroid(vertices, 'jaw_angle_R')
    
    # Орбиты
    orbit_L = _zone_centroid(vertices, 'orbit_L')
    orbit_R = _zone_centroid(vertices, 'orbit_R')
    
    # Вектор перекоса (разница высот)
    jaw_skew = abs(jaw_L[1] - jaw_R[1])
    orbit_skew = abs(orbit_L[1] - orbit_R[1])
    
    return {
        "asymmetry_jaw_skew": float(jaw_skew),
        "asymmetry_orbit_skew": float(orbit_skew),
        "asymmetry_total_vector": float(jaw_skew + orbit_skew)
    }


def compute_ligament_distances(vertices: np.ndarray, bucket: str) -> dict[str, float]:
    """
    [ITER-1.2] Дистанция до связочных якорей.
    Проверяет видимость зоны перед расчетом.
    """
    metrics = {}
    
    # Скуловая связка (Zygomatic Ligament)
    if 'left' in bucket or bucket == 'frontal':
        l_zyg_L = _zone_centroid(vertices, 'ligament_zygomatic_L')
        metrics['ligament_zygomatic_L_depth'] = float(l_zyg_L[2])
        
    if 'right' in bucket or bucket == 'frontal':
        l_zyg_R = _zone_centroid(vertices, 'ligament_zygomatic_R')
        metrics['ligament_zygomatic_R_depth'] = float(l_zyg_R[2])
        
    return metrics


def compute_volume_indices(vertices: np.ndarray, bucket: str) -> dict[str, float]:
    """
    [ITER-2.1] Индексы объема и дефицита тканей.
    """
    metrics = {}
    
    # 1. Neurocranium (Ширина лба к височным ямкам) - только фронтально
    if bucket == 'frontal':
        temp_L = _zone_centroid(vertices, 'temporal_L')
        temp_R = _zone_centroid(vertices, 'temporal_R')
        metrics['index_neurocranium_width'] = float(np.linalg.norm(temp_L - temp_R))
        
    # 2. Facial BMI (Выпуклость щек) - только профили
    if 'profile' in bucket:
        # Для профиля берем только видимую сторону
        side = 'L' if 'left' in bucket else 'R'
        cheek_bone = _zone_centroid(vertices, f'cheekbone_{side}')
        cheek_soft = _zone_centroid(vertices, f'cheek_soft_{side}')
        # Проекция разницы на ось Z (глубина)
        metrics[f'facial_bmi_{side}'] = float(cheek_soft[2] - cheek_bone[2])
        
    return metrics



def _transform_vertices_2d_to_original(vertices_2d_224: np.ndarray, trans_params: np.ndarray) -> np.ndarray:
    """
    [PIPE-FIX] Transform vertices_2d from 3DDFA's 224x224 crop space
    to original image coordinates, matching the 3DDFA model's own
    extractTexNew logic (recon.py lines 636-638).

    Steps (same as 3DDFA's back_resize_ldms):
      1. Flip Y: image Y is top-down, 3DDFA crop Y is bottom-up
      2. Add crop offset (left, up)
      3. Scale back to original image dimensions
    """
    v2d = vertices_2d_224.copy()
    target_size = 224

    # Step 1: Flip Y (3DDFA crop convention: Y=0 at bottom)
    v2d[:, 1] = target_size - 1 - v2d[:, 1]

    # Step 2-3: back_resize_ldms logic
    w0, h0, s = float(trans_params[0]), float(trans_params[1]), float(trans_params[2])
    cx, cy = float(trans_params[3]), float(trans_params[4])

    w = int(w0 * s)
    h = int(h0 * s)
    left = int(w / 2 - target_size / 2 + (cx - w0 / 2) * s)
    up = int(h / 2 - target_size / 2 + (h0 / 2 - cy) * s)

    v2d[:, 0] = (v2d[:, 0] + left) / w * w0
    v2d[:, 1] = (v2d[:, 1] + up) / h * h0

    return v2d


def _recon_dict(reconstruction: Any) -> dict[str, Any]:
    # [PIPE-FIX] Transform vertices_2d from 224x224 crop space to original image coords.
    # Without this, the UV baker samples from the wrong part of the image (black background).
    # This matches 3DDFA's own extractTexNew logic (recon.py lines 636-638):
    #   1. Flip Y: v2d[:, 1] = 224 - 1 - v2d[:, 1]
    #   2. back_resize_ldms to original image coordinates
    v2d_224 = reconstruction.vertices_image[:, :2]
    tp = reconstruction.trans_params
    if tp is not None:
        v2d_orig = _transform_vertices_2d_to_original(v2d_224, tp)
    else:
        v2d_orig = v2d_224

    return {
        "triangles": reconstruction.triangles,
        "uv_coords": reconstruction.uv_coords,
        "vertices": reconstruction.vertices_world,  # [SYS-08] Required by UV generator
        "vertices_2d": v2d_orig,
        "vertices_3d": reconstruction.vertices_camera,
        "visible_idx_renderer": reconstruction.visible_idx_renderer,
        "angles_deg": reconstruction.angles_deg,
    }


def _save_small_render_images(raw_result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    artifacts: dict[str, str] = {}

    def _save_rgb(name: str, value: Any) -> None:
        arr = np.asarray(value)
        if arr.ndim == 4:
            arr = arr[0]
        arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        target = output_dir / f"{name}.png"
        cv2.imwrite(str(target), bgr)
        artifacts[name] = target.name

    def _save_mask(name: str, value: Any) -> None:
        arr = np.asarray(value)
        if arr.ndim == 4:
            arr = arr[0, :, :, 0]
        elif arr.ndim == 3 and arr.shape[-1] == 1:
            arr = arr[:, :, 0]
        arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        target = output_dir / f"{name}.png"
        cv2.imwrite(str(target), arr)
        artifacts[name] = target.name

    _save_rgb("render_face", raw_result["render_face"])
    _save_rgb("render_shape", raw_result["render_shape"])
    _save_mask("render_mask", raw_result["render_mask"])
    return artifacts


def _save_face_crop(image_bgr: np.ndarray, reconstruction: Any, output_dir: Path) -> str:
    """
    [PIPE-FIX] Skin-only face crop using seg_visible from 3DDFA (like v2 script).
    Projects the 224x224 skin mask back to original image coordinates.
    """
    seg_visible = reconstruction.payload.get("seg_visible")
    trans_params = reconstruction.trans_params
    if seg_visible is None or trans_params is None:
        return ""

    h, w = image_bgr.shape[:2]

    # 3DDFA seg channels: [right_eye, left_eye, right_eyebrow, left_eyebrow, nose, up_lip, down_lip, skin]
    skin_224 = seg_visible[:, :, 7].copy()
    # Exclude eyes (0,1), eyebrows (2,3), lips (5,6)
    for i in [0, 1, 2, 3, 5, 6]:
        part_mask = seg_visible[:, :, i]
        skin_224[part_mask > 0.5] = 0

    # Project from 224x224 to original image using back_resize_crop_img
    try:
        sys.path.insert(0, str(REPO_ROOT / "core" / "3ddfa_v3"))
        from util.io import back_resize_crop_img
        from PIL import Image as PILImage

        mask_rgb = np.stack((skin_224, skin_224, skin_224), axis=-1).astype(np.uint8) * 255
        blank = np.zeros((h, w, 3), dtype=np.uint8)
        full_mask_rgb = back_resize_crop_img(mask_rgb, trans_params, blank, resample_method=PILImage.NEAREST)
        mask = full_mask_rgb[:, :, 0]
    except Exception:
        mask = cv2.resize(skin_224, (w, h), interpolation=cv2.INTER_NEAREST)

    # Find bounding box of mask
    coords = cv2.findNonZero(mask)
    if coords is None:
        return ""

    x, y, bw, bh = cv2.boundingRect(coords)
    pad_x = int(bw * 0.15)
    pad_y = int(bh * 0.15)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(w, x + bw + pad_x)
    y2 = min(h, y + bh + pad_y)

    face_crop = cv2.bitwise_and(image_bgr, image_bgr, mask=mask)
    face_crop = face_crop[y1:y2, x1:x2]
    target = output_dir / "face_crop.jpg"
    cv2.imwrite(str(target), face_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    return target.name


def _save_uv_assets(image_bgr: np.ndarray, reconstruction: Any, output_dir: Path) -> dict[str, str]:
    runtime = get_runtime()
    _uv_tex_analysis, uv_tex_beauty, _uv_mask, uv_conf, _aux = runtime.uv.generate(image_bgr, _recon_dict(reconstruction))
    texture_path = output_dir / "uv_texture.png"
    conf_path = output_dir / "uv_confidence.png"
    cv2.imwrite(str(texture_path), uv_tex_beauty)
    conf_uint8 = np.clip(uv_conf * 255.0, 0, 255).astype(np.uint8)
    cv2.imwrite(str(conf_path), conf_uint8)
    return {
        "uv_texture": texture_path.name,
        "uv_confidence": conf_path.name,
    }


def _save_mesh_assets(reconstruction: Any, texture_filename: str, output_dir: Path) -> dict[str, str]:
    obj_path = output_dir / "mesh.obj"
    mtl_path = output_dir / "mesh.mtl"
    vertices = reconstruction.vertices_world
    normals = reconstruction.normals_world
    uv_coords = reconstruction.uv_coords
    triangles = reconstruction.triangles

    mtl_path.write_text(
        "\n".join(
            [
                "newmtl FaceMaterial",
                "Ka 1.000 1.000 1.000",
                "Kd 1.000 1.000 1.000",
                "Ks 0.000 0.000 0.000",
                f"map_Kd {texture_filename}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with obj_path.open("w", encoding="utf-8") as handle:
        handle.write("mtllib mesh.mtl\n")
        handle.write("usemtl FaceMaterial\n")
        for vertex in vertices:
            handle.write(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}\n")
        if uv_coords is not None:
            for uv in uv_coords:
                handle.write(f"vt {uv[0]:.6f} {1.0 - uv[1]:.6f}\n")
        for normal in normals:
            handle.write(f"vn {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}\n")
        for triangle in triangles:
            a, b, c = (int(index) + 1 for index in triangle.tolist())
            handle.write(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n")

    return {"mesh_obj": obj_path.name, "mesh_mtl": mtl_path.name}


def extract_photo_bundle(
    source_path: Path,
    dataset: str,
    photo_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    runtime = get_runtime()
    ensure_directory(output_dir)

    image_bgr = cv2.imread(str(source_path))
    if image_bgr is None:
        raise RuntimeError(f"Не удалось прочитать изображение: {source_path}")

    pose = runtime.pose_detector.get_pose(source_path)
    bucket = str(pose.get("bucket", "unclassified"))
    angle = RAW_BUCKET_TO_UI.get(bucket, "unknown")

    reconstruction = resolve_reconstruction(
        runtime.reconstruction,
        source_path,
        output_dir,
        neutral_expression=False,
    )

    raw_result = reconstruction.payload.get("raw_result", {})
    # [PIPE-FIX] Skip render_face/render_shape/render_mask — not needed for pipeline.
    # Only extract UV texture, mask, confidence, mesh, and face crop (like v2 script).
    uv_artifacts = _save_uv_assets(image_bgr, reconstruction, output_dir) if runtime.uv else {}
    mesh_artifacts = _save_mesh_assets(reconstruction, uv_artifacts.get("uv_texture", "uv_texture.png"), output_dir) if uv_artifacts else {}

    # Build face crop from seg_visible (like v2 script's apply_segmentation_mask)
    face_crop_name = _save_face_crop(image_bgr, reconstruction, output_dir)

    # Copy original photo to output directory for UI use
    import shutil
    original_copy_name = source_path.name
    shutil.copy2(source_path, output_dir / original_copy_name)

    # Texture analysis on face_crop.jpg (like v2 script — masked crop, no separate mask needed)
    face_crop_path = output_dir / face_crop_name if face_crop_name else None
    texture_forensics = runtime.texture.analyze_image(face_crop_path or source_path, None)
    quality = runtime.quality.evaluate(source_path)
    geometry_metrics, pose_reliability = _compute_geometry_metrics(reconstruction, bucket)


    # Итоговый вес достоверности: текстурная четкость * геометрическая стабильность (поза)
    final_reliability = float(texture_forensics.get("reliability_weight", 1.0)) * pose_reliability

    metrics = {
        **geometry_metrics,
        "reliability_weight": final_reliability,
        "texture_lbp_complexity": float(texture_forensics.get("lbp_complexity", 0.0)),
        "texture_lbp_uniformity": float(texture_forensics.get("lbp_uniformity", 0.0)),
        "texture_specular_gloss": float(texture_forensics.get("specular_gloss", 0.0)),
        "texture_max_reflectance": float(texture_forensics.get("max_reflectance", 0.0)),
        "texture_silicone_prob": float(texture_forensics.get("silicone_probability", 0.0)),
        "texture_pore_density": float(texture_forensics.get("pore_density", 0.0)),
        "texture_spot_density": float(texture_forensics.get("spot_density", 0.0)),
        "texture_wrinkle_forehead": float(texture_forensics.get("wrinkle_forehead", 0.0)),
        "texture_wrinkle_nasolabial": float(texture_forensics.get("wrinkle_nasolabial", 0.0)),
        "texture_global_smoothness": float(texture_forensics.get("global_smoothness", 0.0)),
    }

    summary = {
        "photo_id": photo_id,
        "dataset": dataset,
        "filename": source_path.name,
        "source_path": str(source_path),
        "file_size_bytes": source_path.stat().st_size,
        "bucket": bucket,
        "angle": angle,
        "bucket_label": angle,
        "pose": {
            "yaw": float(pose.get("yaw", 0.0)),
            "pitch": float(pose.get("pitch", 0.0)),
            "roll": float(pose.get("roll", 0.0)),
            "bucket": bucket,
            "pose_source": pose.get("pose_source"),
            "needs_manual_review": bool(pose.get("needs_manual_review", False)),
        },
        "reconstruction": {
            "angles_deg": [float(value) for value in np.asarray(reconstruction.angles_deg).reshape(-1).tolist()],
            "vertex_count": int(reconstruction.vertices_world.shape[0]),
            "triangle_count": int(reconstruction.triangles.shape[0]),
        },
        "quality": quality,
        "texture_forensics": texture_forensics,
        "metrics": metrics,
        "selected_metric_keys": BUCKET_METRIC_KEYS.get(bucket, BUCKET_METRIC_KEYS["unclassified"]),
        "artifacts": {
            **uv_artifacts,
            **mesh_artifacts,
            "original_photo": original_copy_name,
        },
        "status": "ready",
        "extracted_at": iso_now(),
        "artifact_version": ARTIFACT_VERSION,
        "runtime_config_hash": ForensicManifest.compute_manifest_id(photo_id, runtime),
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def recompute_metric_subset(
    source_path: Path,
    dataset: str,
    photo_id: str,
    output_dir: Path,
    metric_keys: list[str],
) -> dict[str, Any]:
    summary = read_json(output_dir / "summary.json", {})
    if not summary:
        return extract_photo_bundle(source_path, dataset, photo_id, output_dir)

    runtime = get_runtime()
    reconstruction = resolve_reconstruction(
        runtime.reconstruction,
        source_path,
        output_dir,
        neutral_expression=False,
    )
    bucket = summary.get("bucket", "unclassified")
    geometry_metrics, pose_reliability = _compute_geometry_metrics(reconstruction, bucket)


    needs_texture = any(key.startswith("texture_") for key in metric_keys)
    texture_forensics = summary.get("texture_forensics", {})
    quality = summary.get("quality", {})
    if needs_texture:
        mask_name = summary.get("artifacts", {}).get("render_mask")
        mask_path = output_dir / mask_name if isinstance(mask_name, str) else None
        texture_forensics = runtime.texture.analyze_image(source_path, mask_path)
    
    final_reliability = float(texture_forensics.get("reliability_weight", 1.0)) * pose_reliability

    if any(key in {"blur_variance", "noise_level"} for key in metric_keys):
        quality = runtime.quality.evaluate(source_path)

    texture_metrics = {
        "reliability_weight": final_reliability,
        "texture_lbp_complexity": float(texture_forensics.get("lbp_complexity", 0.0)),
        "texture_lbp_uniformity": float(texture_forensics.get("lbp_uniformity", 0.0)),
        "texture_specular_gloss": float(texture_forensics.get("specular_gloss", 0.0)),
        "texture_max_reflectance": float(texture_forensics.get("max_reflectance", 0.0)),
        "texture_silicone_prob": float(texture_forensics.get("silicone_probability", 0.0)),
        "texture_pore_density": float(texture_forensics.get("pore_density", 0.0)),
        "texture_spot_density": float(texture_forensics.get("spot_density", 0.0)),
        "texture_wrinkle_forehead": float(texture_forensics.get("wrinkle_forehead", 0.0)),
        "texture_wrinkle_nasolabial": float(texture_forensics.get("wrinkle_nasolabial", 0.0)),
        "texture_global_smoothness": float(texture_forensics.get("global_smoothness", 0.0)),
    }

    merged_metrics = {**summary.get("metrics", {})}
    available_metrics = {**geometry_metrics, **texture_metrics}
    for key in metric_keys:
        if key in available_metrics:
            merged_metrics[key] = available_metrics[key]
        elif key == "blur_variance":
            merged_metrics[key] = float(quality.get("blur_variance", 0.0))
        elif key == "noise_level":
            merged_metrics[key] = float(quality.get("noise_level", 0.0))

    summary["metrics"] = merged_metrics
    summary["quality"] = quality
    summary["texture_forensics"] = texture_forensics
    summary["updated_at"] = iso_now()
    summary["artifact_version"] = ARTIFACT_VERSION
    summary["runtime_config_hash"] = ForensicManifest.compute_manifest_id(photo_id, runtime)
    write_json(output_dir / "summary.json", summary)
    return summary
