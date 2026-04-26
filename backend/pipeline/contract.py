from __future__ import annotations

# Unified Export Contract V2
# Consolidates old export_contract.py and downstream_export_contract.py

EXPORT_CONTRACT_VERSION = '2.0'

# --- Common Field Definitions ---
COMMON_ZONE_FIELDS = [
    'name',
    'status',
    'analysis_role',
    'bone_priority_class',
    'bone_weight',
    'raw_error',
    'bounded_score',
    'principal_shift_axis',
    'dominant_shift_direction',
]

PAIRWISE_FEATURE_FIELDS = [
    'metadata.image_a',
    'metadata.image_b',
    'summary.status',
    'summary.comparison_bucket_key',
    'summary.interpretation_mode',
    'summary.shared_visibility_quality',
    'summary.calibration_context',
    'summary.bone_structure_summary',
    'score.raw_geometry_error',
    'score.robust_geometry_error',
    'score.bone_raw_geometry_error',
    'score.bone_bounded_similarity_score',
    'score.provisional_band',
]

FORENSIC_PASSPORT_FIELDS = [
    'metadata.entity_tag',
    'metadata.photo_id',
    'texture_forensics.lbp_complexity',
    'texture_forensics.silicone_probability',
    'texture_forensics.verdict',
    'anomaly_flags',
    'temporal_metadata',
]

def map_confidence_level(provisional_band: str | None, texture_forensics: dict | None = None) -> str:
    """
    Maps internal band statuses and texture data to a strict UI contract:
    acceptable | unlikely | impossible
    """
    if texture_forensics:
        silicone_prob = float(texture_forensics.get('silicone_probability', 0.0))
        if silicone_prob > 0.85:
            return "impossible" # Mask detected
        if silicone_prob > 0.6:
            return "unlikely"

    if not provisional_band or provisional_band == "unavailable":
        return "acceptable"

    pb = str(provisional_band).lower()

    if "same_person" in pb:
        return "acceptable"
    if "gray_zone" in pb or "uncertain" in pb:
        return "unlikely"
    if "different_person" in pb:
        return "impossible"

    return "acceptable"

def attach_ui_confidence_level(payload: dict[str, object]) -> dict[str, object]:
    """
    Normalizes confidenceLevel for UI in any pairwise/calibrated/passport payload.
    """
    if not isinstance(payload, dict):
        return payload

    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    provisional_band = (
        score.get("provisional_band")
        or score.get("robust_provisional_band")
        or score.get("bone_provisional_band")
    )

    tf = payload.get("texture_forensics")
    if not tf and "stable_features" in payload:
        sf = payload.get("stable_features", {})
        if isinstance(sf, dict):
            tf = sf.get("texture_forensics")

    payload["confidenceLevel"] = map_confidence_level(provisional_band, texture_forensics=tf)
    return payload
