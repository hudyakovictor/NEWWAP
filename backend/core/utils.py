from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

RAW_BUCKET_TO_UI = {
    "frontal": "frontal",
    "left_profile": "left-profile",
    "right_profile": "right-profile",
    "left_threequarter_mid": "left-3-4-mid",
    "right_threequarter_mid": "right-3-4-mid",
    "left_threequarter_light": "slight-left",
    "right_threequarter_light": "slight-right",
    "left_threequarter_deep": "left-3-4-deep",
    "right_threequarter_deep": "right-3-4-deep",
    "unclassified": "unknown",
}

UI_TO_RAW_BUCKET = {value: key for key, value in RAW_BUCKET_TO_UI.items()}

BUCKET_LABELS = {
    "frontal": "Анфас",
    "left_profile": "Левый профиль",
    "right_profile": "Правый профиль",
    "left_threequarter_mid": "Левые 3/4 средние",
    "right_threequarter_mid": "Правые 3/4 средние",
    "left_threequarter_light": "Лёгкий поворот влево",
    "right_threequarter_light": "Лёгкий поворот вправо",
    "left_threequarter_deep": "Левые 3/4 глубокие",
    "right_threequarter_deep": "Правые 3/4 глубокие",
    "unclassified": "Не классифицировано",
}

BUCKET_METRIC_KEYS = {
    "frontal": [
        "cranial_face_index", "jaw_width_ratio", "canthal_tilt_L", "canthal_tilt_R",
        "gonial_angle_L", "gonial_angle_R", "chin_offset_asymmetry", "nose_width_ratio",
        "texture_silicone_prob", "texture_pore_density", "texture_spot_density", 
        "texture_wrinkle_forehead", "texture_global_smoothness"
    ],
    "left_threequarter_light": [
        "cranial_face_index", "orbit_depth_L_ratio", "canthal_tilt_L", "nose_projection_ratio", 
        "jaw_width_ratio", "nasal_frontal_index", "gonial_angle_L",
        "texture_silicone_prob", "texture_pore_density", "texture_wrinkle_forehead", 
        "texture_wrinkle_nasolabial", "texture_global_smoothness"
    ],
    "right_threequarter_light": [
        "cranial_face_index", "orbit_depth_R_ratio", "canthal_tilt_R", "nose_projection_ratio", 
        "jaw_width_ratio", "nasal_frontal_index", "gonial_angle_R",
        "texture_silicone_prob", "texture_pore_density", "texture_wrinkle_forehead", 
        "texture_wrinkle_nasolabial", "texture_global_smoothness"
    ],
    "left_threequarter_mid": [
        "orbit_depth_L_ratio", "chin_projection_ratio", "nose_projection_ratio", 
        "jaw_width_ratio", "nasofacial_angle_ratio", "forehead_slope_index",
        "texture_silicone_prob", "texture_pore_density", "texture_wrinkle_forehead", 
        "texture_wrinkle_nasolabial", "texture_global_smoothness"
    ],
    "right_threequarter_mid": [
        "orbit_depth_R_ratio", "chin_projection_ratio", "nose_projection_ratio", 
        "jaw_width_ratio", "nasofacial_angle_ratio", "forehead_slope_index",
        "texture_silicone_prob", "texture_pore_density", "texture_wrinkle_forehead", 
        "texture_wrinkle_nasolabial", "texture_global_smoothness"
    ],
    "left_threequarter_deep": [
        "orbit_depth_L_ratio", "chin_projection_ratio", "nasofacial_angle_ratio", 
        "forehead_slope_index", "jaw_width_ratio", "nose_projection_ratio",
        "texture_silicone_prob", "texture_pore_density", "texture_wrinkle_forehead", 
        "texture_wrinkle_nasolabial", "texture_global_smoothness"
    ],
    "right_threequarter_deep": [
        "orbit_depth_R_ratio", "chin_projection_ratio", "nasofacial_angle_ratio", 
        "forehead_slope_index", "jaw_width_ratio", "nose_projection_ratio",
        "texture_silicone_prob", "texture_pore_density", "texture_wrinkle_forehead", 
        "texture_wrinkle_nasolabial", "texture_global_smoothness"
    ],
    "left_profile": [
        "nose_projection_ratio", "chin_projection_ratio", "nasofacial_angle_ratio", 
        "forehead_slope_index", "orbit_depth_L_ratio", "cranial_face_index",
        "texture_silicone_prob", "texture_pore_density", "texture_wrinkle_forehead", 
        "texture_wrinkle_nasolabial", "texture_global_smoothness"
    ],
    "right_profile": [
        "nose_projection_ratio", "chin_projection_ratio", "nasofacial_angle_ratio", 
        "forehead_slope_index", "orbit_depth_R_ratio", "cranial_face_index",
        "texture_silicone_prob", "texture_pore_density", "texture_wrinkle_forehead", 
        "texture_wrinkle_nasolabial", "texture_global_smoothness"
    ],
    "unclassified": [
        "cranial_face_index", "jaw_width_ratio", "interorbital_ratio", 
        "texture_silicone_prob", "texture_pore_density", "texture_global_smoothness"
    ],
}

FORENSIC_RADAR_AXES = {
    "Cranial": ["cranial_face_index", "forehead_slope_index"],
    "Orbital": ["orbit_depth_L_ratio", "orbit_depth_R_ratio", "canthal_tilt_L", "canthal_tilt_R"],
    "Mandibular": ["jaw_width_ratio", "gonial_angle_L", "gonial_angle_R"],
    "Nasal": ["nose_width_ratio", "nose_projection_ratio", "nasal_frontal_index"],
    "Symmetry": ["chin_offset_asymmetry", "orbital_asymmetry_index"],
    "Texture": ["texture_pore_density", "texture_lbp_complexity"],
    "Material": ["texture_silicone_prob", "texture_specular_gloss"],
    "Stability": ["reliability_weight"],
}

ALL_BUCKETS = [
    "frontal",
    "left_threequarter_light",
    "right_threequarter_light",
    "left_threequarter_mid",
    "right_threequarter_mid",
    "left_threequarter_deep",
    "right_threequarter_deep",
    "left_profile",
    "right_profile",
]

DATE_PATTERNS = [
    re.compile(r"(\d{4})_(\d{2})_(\d{2})"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"(\d{4})(\d{2})(\d{2})"),
    re.compile(r"(\d{4})"),
]


def runtime_config_snapshot(runtime: Any) -> dict[str, Any]:
    """
    Создает снимок текущей конфигурации системы для включения в ForensicManifest.
    Обеспечивает воспроизводимость результатов.
    """
    from .constants import ARTIFACT_VERSION, MIN_ZONE_VERTICES, VISIBILITY_ANGLE_DEG, SILICONE_SIGMOID_BIAS
    
    return {
        "artifact_version": ARTIFACT_VERSION,
        "min_zone_vertices": MIN_ZONE_VERTICES,
        "visibility_angle_threshold_deg": VISIBILITY_ANGLE_DEG,
        "silicone_sigmoid_bias": SILICONE_SIGMOID_BIAS,
        "device": getattr(runtime, "device", "unknown"),
        "timestamp": iso_now(),
    }


class ForensicManifest:
    """
    Центральный манифест для аудита форензик-артефактов.
    """
    @staticmethod
    def compute_manifest_id(photo_id: str, runtime: Any) -> str:
        snapshot = runtime_config_snapshot(runtime)
        payload = f"{photo_id}:{json.dumps(snapshot, sort_keys=True)}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def list_image_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files = [path for path in root.rglob("*") if is_image_file(path)]
    files.sort(key=lambda item: item.name.lower())
    return files


def parse_date_from_name(filename: str) -> tuple[str, date | None]:
    stem = Path(filename).stem
    stem = re.sub(r"-\d{1,2}$", "", stem)
    for pattern in DATE_PATTERNS:
        match = pattern.search(stem)
        if not match:
            continue
        parts = match.groups()
        try:
            if len(parts) == 3:
                dt = date(int(parts[0]), int(parts[1]), int(parts[2]))
            else:
                dt = date(int(parts[0]), 1, 1)
            return dt.isoformat(), dt
        except ValueError:
            continue
    return "", None


def fallback_date_for_file(path: Path) -> tuple[str, date]:
    ts = datetime.fromtimestamp(path.stat().st_mtime)
    return ts.date().isoformat(), ts.date()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9а-яё._-]+", "-", value)
    value = value.strip("-")
    return value or "file"


def stable_photo_id(dataset: str, path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.name
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:10]
    return f"{dataset}-{slugify(path.stem)}-{digest}"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def bytes_to_human(value: int) -> str:
    if value >= 1024**3:
        return f"{value / 1024**3:.2f} GB"
    if value >= 1024**2:
        return f"{value / 1024**2:.1f} MB"
    if value >= 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value} B"


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            total += (Path(root) / name).stat().st_size
    return total


def median(values: Iterable[float]) -> float:
    seq = sorted(float(v) for v in values)
    if not seq:
        return 0.0
    mid = len(seq) // 2
    if len(seq) % 2:
        return seq[mid]
    return (seq[mid - 1] + seq[mid]) / 2.0


def mad(values: Iterable[float]) -> float:
    seq = [float(v) for v in values]
    if not seq:
        return 0.0
    m = median(seq)
    return median(abs(v - m) for v in seq)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

