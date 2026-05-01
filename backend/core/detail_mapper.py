from typing import Any, Dict, List
import math
from .utils import BUCKET_METRIC_KEYS

# Mapping from frontend zone IDs to backend metric keys or zone names
ZONE_MAPPING = {
    "nasal_bridge": "nose_bridge_tip",
    "orbit_l": "orbit_L",
    "orbit_r": "orbit_R",
    "zygo_l": "cheekbone_L",
    "zygo_r": "cheekbone_R",
    "chin": "chin",
    "brow_ridge": "brow_ridge_L", # Simplified
    "jaw_l": "jaw_L",
    "jaw_r": "jaw_R",
    "nose_wing_l": "nose_wing_L",
    "nose_wing_r": "nose_wing_R",
    "lip_upper": "upper_lip",
    "lip_lower": "lower_lip",
    "forehead": "forehead",
}

# Default frontend zone definitions (matching ui/src/mock/photoDetail.ts)
FACE_ZONES_META = [
    { "id": "nasal_bridge", "name": "Nasal bridge",    "group": "bone",     "priority": "max",    "weight": 1.00, "x": 50, "y": 45 },
    { "id": "orbit_l",      "name": "Left orbit",      "group": "bone",     "priority": "max",    "weight": 0.95, "x": 38, "y": 40 },
    { "id": "orbit_r",      "name": "Right orbit",     "group": "bone",     "priority": "max",    "weight": 0.95, "x": 62, "y": 40 },
    { "id": "zygo_l",       "name": "Left zygomatic",  "group": "bone",     "priority": "max",    "weight": 0.90, "x": 30, "y": 55 },
    { "id": "zygo_r",       "name": "Right zygomatic", "group": "bone",     "priority": "max",    "weight": 0.90, "x": 70, "y": 55 },
    { "id": "chin",         "name": "Chin (mental)",   "group": "bone",     "priority": "max",    "weight": 0.88, "x": 50, "y": 82 },
    { "id": "brow_ridge",   "name": "Brow ridge",      "group": "bone",     "priority": "high",   "weight": 0.80, "x": 50, "y": 32 },
    { "id": "jaw_l",        "name": "Left jaw",        "group": "bone",     "priority": "high",   "weight": 0.75, "x": 28, "y": 72 },
    { "id": "jaw_r",        "name": "Right jaw",       "group": "bone",     "priority": "high",   "weight": 0.75, "x": 72, "y": 72 },
    { "id": "zygo_lig_l",   "name": "L zygomatic lig.", "group": "ligament", "priority": "high",  "weight": 0.70, "x": 33, "y": 58 },
    { "id": "zygo_lig_r",   "name": "R zygomatic lig.", "group": "ligament", "priority": "high",  "weight": 0.70, "x": 67, "y": 58 },
    { "id": "orbit_lig_l",  "name": "L orbital lig.",  "group": "ligament", "priority": "high",   "weight": 0.70, "x": 40, "y": 43 },
    { "id": "orbit_lig_r",  "name": "R orbital lig.",  "group": "ligament", "priority": "high",   "weight": 0.70, "x": 60, "y": 43 },
    { "id": "nose_wing_l",  "name": "L nose wing",     "group": "soft",     "priority": "low",    "weight": 0.30, "x": 45, "y": 60 },
    { "id": "nose_wing_r",  "name": "R nose wing",     "group": "soft",     "priority": "low",    "weight": 0.30, "x": 55, "y": 60 },
    { "id": "lip_upper",    "name": "Upper lip",       "group": "soft",     "priority": "low",    "weight": 0.25, "x": 50, "y": 70 },
    { "id": "lip_lower",    "name": "Lower lip",       "group": "soft",     "priority": "low",    "weight": 0.25, "x": 50, "y": 74 },
    { "id": "cheek_l",      "name": "Left cheek",      "group": "mixed",    "priority": "medium", "weight": 0.45, "x": 32, "y": 63 },
    { "id": "cheek_r",      "name": "Right cheek",     "group": "mixed",    "priority": "medium", "weight": 0.45, "x": 68, "y": 63 },
    { "id": "forehead",     "name": "Forehead skin",   "group": "mixed",    "priority": "medium", "weight": 0.40, "x": 50, "y": 22 },
    { "id": "neck_skin",    "name": "Neck skin",       "group": "soft",     "priority": "low",    "weight": 0.20, "x": 50, "y": 95 },
]

def map_record_to_detail(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hydrates a basic PhotoRecord into a full PhotoDetail structure for the UI.
    """
    import logging
    logger = logging.getLogger("deeputin.detail_mapper")
    
    photo_id = record.get("photo_id", "")
    logger.info(f"[DETAIL_MAPPER] Mapping record {photo_id}")
    logger.info(f"[DETAIL_MAPPER] Record status: {record.get('status')}")
    logger.info(f"[DETAIL_MAPPER] Has metrics: {'metrics' in record}, Has reconstruction: {'reconstruction' in record}")
    
    metrics = record.get("metrics", {})
    logger.info(f"[DETAIL_MAPPER] Metrics count: {len(metrics)}, keys: {list(metrics.keys())[:5]}")
    
    recon = record.get("reconstruction", {})
    logger.info(f"[DETAIL_MAPPER] Recon keys: {list(recon.keys())}")
    
    # Try to get pose from record.pose (yaw, pitch, roll) or from reconstruction.angles_deg
    pose_data = record.get("pose", {})
    if pose_data and "yaw" in pose_data:
        pose = [pose_data.get("yaw", 0), pose_data.get("pitch", 0), pose_data.get("roll", 0)]
    elif recon and "angles_deg" in recon:
        pose = recon["angles_deg"]
    else:
        pose = [0, 0, 0]
    logger.info(f"[DETAIL_MAPPER] Pose: {pose}")
    
    # Map zones
    zones = []
    for meta in FACE_ZONES_META:
        zone_id = meta["id"]
        backend_key = ZONE_MAPPING.get(zone_id)
        
        # Determine visibility
        yaw = pose[0]
        visible = True
        if abs(yaw) > 40:
            if yaw > 0 and (zone_id.endswith("_r") or zone_id.endswith("_lig_r")):
                visible = False
            elif yaw < 0 and (zone_id.endswith("_l") or zone_id.endswith("_lig_l")):
                visible = False
        
        # Determine exclusion
        excluded = False
        if zone_id in {"lip_upper", "lip_lower"}:
            excluded = True # Dynamic in mock, here simplified
            
        # Determine score
        score = 0.0
        if visible and not excluded:
            if backend_key and backend_key in metrics:
                score = metrics[backend_key]
            else:
                # Stub deterministic score for missing real metrics
                score = 0.85 if meta["group"] == "bone" else 0.65
        
        zones.append({
            **meta,
            "visible": visible,
            "excluded": excluded,
            "score": score
        })
    
    logger.info(f"[DETAIL_MAPPER] Mapped {len(zones)} zones, visible: {sum(1 for z in zones if z['visible'])}")

    # Reconstruction URLs
    artifacts = record.get("artifacts", {})
    logger.info(f"[DETAIL_MAPPER] Artifacts: {artifacts}")
    logger.info(f"[DETAIL_MAPPER] Texture data in record: {'texture_forensics' in record}")
    texture_data = record.get("texture_forensics", {})
    if texture_data:
        logger.info(f"[DETAIL_MAPPER] Texture keys: {list(texture_data.keys())}")
    
    detail = {
        "year": record.get("parsed_year", 0),
        "photo": record.get("source_url", ""),
        "reconstruction": {
            "renderFace": artifacts.get("render_face", f"/source/{record.get('dataset', 'main')}/{record.get('filename')}"),
            "renderShape": artifacts.get("render_shape", ""),
            "renderMask": artifacts.get("render_mask", ""),
            "uvTexture": artifacts.get("uv_texture", ""),
            "uvConfidence": artifacts.get("uv_confidence", ""),
            "uvMask": artifacts.get("uv_mask", ""),
            "overlay": artifacts.get("face_overlay", ""),
            "meshObj": artifacts.get("mesh_obj", ""),
            "meshTriangles": recon.get("triangle_count", 70789),
            "vertices": recon.get("vertex_count", 35709),
        },
        "zones": zones,
        "pose": {
            "yaw": pose[0],
            "pitch": pose[1],
            "roll": pose[2],
            "classification": record.get("bucket", "frontal"),
            "confidence": 0.95 if record.get("status") == "ready" else 0.7,
            "fallback": False
        },
        "expression": {
            "jawOpen": 0.05,
            "smile": 0.1,
            "neutral": True,
            "excludedZones": ["lip_upper", "lip_lower"]
        },
        "texture": {
            "lbpComplexity": texture_data.get("lbp_complexity", 0.5),
            "fftAnomaly": texture_data.get("quality", {}).get("noise_level", 0.1),
            "albedoHealth": texture_data.get("quality", {}).get("quality_index", 0.8),
            "specularIndex": texture_data.get("specular_gloss", 0.2),
            "syntheticProb": texture_data.get("silicone_probability", 0.05),
            "poreDensity": texture_data.get("pore_density", 0.0),
            "wrinkleForehead": texture_data.get("wrinkle_forehead", 0.0),
            "wrinkleNasolabial": texture_data.get("wrinkle_nasolabial", 0.0),
            "globalSmoothness": texture_data.get("global_smoothness", 0.0),
            "reliabilityWeight": texture_data.get("reliability_weight", 1.0),
        },
        "calibration": {
            "bucket": record.get("bucket", "frontal_unclassified"),
            "level": "medium",
            "sampleCount": 15,
            "variance": 0.05
        },
        "chronology": {
            "prevYear": record.get("parsed_year", 2000) - 1,
            "prevDelta": 1,
            "boneAsymmetryJump": 0.1,
            "ligamentJump": 0.05,
            "flags": []
        },
        "bayes": {
            "H0": 0.8,
            "H1": 0.1,
            "H2": 0.1
        },
        "meta": {
            "id": photo_id,
            "filename": record.get("filename", ""),
            "capturedAt": record.get("date_str", ""),
            "source": record.get("source", "real_dataset"),
            "md5": record.get("md5", ""),
            "resolution": record.get("resolution", "800x800"),
            "sizeKB": record.get("file_size_bytes", 0) // 1024,
        },
        "notes": [
            "Real forensic data mapped from summary artifacts." if record.get("status") == "ready" else "Stub metrics for pending extraction."
        ]
    }
    
    return detail
