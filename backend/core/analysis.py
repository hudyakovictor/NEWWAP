from __future__ import annotations

import math
import threading
from pathlib import Path
import sys
from typing import Any

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
from uv_module.hd_uv_generator import HDUVConfig, HDUVTextureGenerator

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


class LegacyRuntime:
    def __init__(self) -> None:
        self.pose_detector = PoseDetector(device="cpu")
        self.reconstruction = ReconstructionAdapter(device="cpu", detector_device="cpu")
        self.texture = SkinTextureAnalyzer()
        self.quality = QualityGate(
            blur_threshold=SETTINGS.blur_threshold,
            noise_threshold=SETTINGS.noise_threshold,
        )
        self.uv = HDUVTextureGenerator(
            HDUVConfig(
                uv_size=768,
                super_sample=1,
                verbose=False,
                enable_delighting=False,
            )
        )


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



def _recon_dict(reconstruction: Any) -> dict[str, Any]:
    return {
        "triangles": reconstruction.triangles,
        "uv_coords": reconstruction.uv_coords,
        "vertices_2d": reconstruction.vertices_image[:, :2],
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


def _save_face_overlay(image_bgr: np.ndarray, mask_path: Path, output_dir: Path) -> str:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return ""
    resized_mask = cv2.resize(mask, (image_bgr.shape[1], image_bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
    colored = image_bgr.copy()
    tint = np.zeros_like(colored)
    tint[:, :, 1] = 180
    alpha = (resized_mask.astype(np.float32) / 255.0)[:, :, None] * 0.45
    overlay = cv2.addWeighted(colored, 1.0, tint, 0.35, 0.0)
    blended = (colored * (1.0 - alpha) + overlay * alpha).astype(np.uint8)
    target = output_dir / "face_overlay.png"
    cv2.imwrite(str(target), blended)
    return target.name


def _save_uv_assets(image_bgr: np.ndarray, reconstruction: Any, output_dir: Path) -> dict[str, str]:
    runtime = get_runtime()
    uv_texture, uv_mask, uv_conf, _aux = runtime.uv.generate(image_bgr, _recon_dict(reconstruction))
    texture_path = output_dir / "uv_texture.png"
    mask_path = output_dir / "uv_mask.png"
    conf_path = output_dir / "uv_confidence.png"
    cv2.imwrite(str(texture_path), uv_texture)
    cv2.imwrite(str(mask_path), (uv_mask.astype(np.uint8) * 255))
    conf_uint8 = np.clip(uv_conf * 255.0, 0, 255).astype(np.uint8)
    cv2.imwrite(str(conf_path), conf_uint8)
    return {
        "uv_texture": texture_path.name,
        "uv_mask": mask_path.name,
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
    render_artifacts = _save_small_render_images(raw_result, output_dir)
    overlay_name = _save_face_overlay(image_bgr, output_dir / render_artifacts["render_mask"], output_dir)
    uv_artifacts = _save_uv_assets(image_bgr, reconstruction, output_dir)
    mesh_artifacts = _save_mesh_assets(reconstruction, uv_artifacts["uv_texture"], output_dir)

    mask_path = output_dir / render_artifacts["render_mask"]
    texture_forensics = runtime.texture.analyze_image(source_path, mask_path)
    quality = runtime.quality.evaluate_image(source_path)
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
            **render_artifacts,
            **uv_artifacts,
            **mesh_artifacts,
            "face_overlay": overlay_name,
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
        quality = runtime.quality.evaluate_image(source_path)

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
