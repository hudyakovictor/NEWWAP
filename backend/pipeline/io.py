from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import ARTIFACT_VERSION
from .contract import export_contract_for_artifact
from .types import ComparisonResult
from core.utils import iso_now, json_ready

def build_forensic_payload(
    result: ComparisonResult,
    image_a: Path,
    image_b: Path,
    output_path: Path,
    runtime_config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    [ITER-0] Standardized Forensic Payload.
    Generates high-integrity JSON for UI consumption.
    """
    payload = {
        "version": ARTIFACT_VERSION,
        "metadata": {
            "artifact_version": ARTIFACT_VERSION,
            "generated_at_utc": iso_now(),
            "image_a": str(image_a),
            "image_b": str(image_b),
            "status": result.status,
            "runtime_config": runtime_config or {},
            "export_contract": export_contract_for_artifact("pairwise"),
        },
        "summary": {
            "status": result.status,
            "provisional_band": result.provisional_band,
            "robust_provisional_band": result.robust_provisional_band,
            "geometry_error": json_ready(result.score_raw),
            "similarity_score": json_ready(result.score_bounded),
        },
        "alignment": {
            "method": "rigid_umeyama_no_scale",
            "residual_after": json_ready(result.alignment.residual_after) if result.alignment else None,
        },
        "zones": [
            {
                "id": zone.name,
                "name": zone.name,
                "error": json_ready(zone.raw_error),
                "score": json_ready(zone.bounded_score),
                "delta_mm": json_ready(zone.delta_mm),
                "shift_direction": zone.dominant_shift_direction,
            }
            for zone in result.zones
        ],
        "diagnostics": json_ready(result.diagnostics)
    }
    return payload

def save_forensic_result(payload: Dict[str, Any], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
