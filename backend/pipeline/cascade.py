from __future__ import annotations

import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

from .quality_gate import QualityGate
from .reconstruction import resolve_reconstruction
from .alignment import rigid_umeyama
from .scoring import align_and_score
from .texture import SkinTextureAnalyzer
from .calibration import CalibrationAnalyzer
from .chronology import ChronologyAnalyzer
from .verdict import (
    BayesianMultiHypothesisEngine,
    ForensicEvidenceSummary,
    ForensicVerdict,
    ForensicStatus,
    FuzzyLabel,
    GeometryEvidenceMode,
    normalize_geometry_evidence_mode,
)
from .compare import PairComparisonEngine

class CascadeEngine:
    """
    [ITER-4] The Cascade Engine.
    Sequences forensic checks:
    - Gate 0: Temporal Consistency (Impossible Shortening)
    - Stage 1: Texture & Quality Fast Check (Silicone Detection)
    - Stage 2: Deep Geometry Analysis (3D SNR)
    - Synthesis: Bayesian Multi-Hypothesis Verdict
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.quality_gate = QualityGate()
        self.texture_analyzer = SkinTextureAnalyzer()
        self.calibration = CalibrationAnalyzer()
        self.chronology = ChronologyAnalyzer()
        self.verdict_engine = BayesianMultiHypothesisEngine()
        self.pair_engine = PairComparisonEngine(calibration=self.calibration)
        from .reconstruction import ReconstructionAdapter
        self.recon_adapter = ReconstructionAdapter()
        self.recon_root = Path(self.config.get("recon_root", REPO_ROOT / "storage" / "recon"))

    def _collect_timeline_flags(
        self,
        timeline_context: Optional[List[Dict[str, Any]]],
        date_a: str,
        date_b: str,
    ) -> List[Dict[str, Any]]:
        if not timeline_context:
            return []

        enriched = self.chronology.analyze_timeline([dict(item) for item in timeline_context])
        collected: List[Dict[str, Any]] = []
        for item in enriched:
            if item.get("extracted_at") in {date_a, date_b}:
                collected.extend(item.get("anomaly_flags", []))
        return collected

    def analyze_pair(
        self,
        photo_a: Path,
        photo_b: Path,
        date_a: str,
        date_b: str,
        timeline_context: Optional[List[Dict[str, Any]]] = None,
    ) -> ForensicVerdict:
        """
        Full cascade analysis of a pair.
        """
        # --- Stage 0: Temporal Gate ---
        # Check for impossible shortening or other immediate red flags
        chron_flags = self.chronology.check_pair_consistency(date_a, date_b)
        chron_flags.extend(self._collect_timeline_flags(timeline_context, date_a, date_b))
        
        # --- Stage 1: Fast Texture/Quality ---
        # Quality Gate
        q_a = self.quality_gate.evaluate(photo_a)
        q_b = self.quality_gate.evaluate(photo_b)
        
        if q_a["is_rejected"] or q_b["is_rejected"]:
            rejected = []
            if q_a["is_rejected"]:
                rejected.append(photo_a.name)
            if q_b["is_rejected"]:
                rejected.append(photo_b.name)
            return ForensicVerdict(
                status=ForensicStatus.UNCERTAIN,
                fuzzy_label=FuzzyLabel.INSUFFICIENT_DATA,
                probabilities={"H0_same": 0.0, "H1_swap": 0.0, "H2_diff": 0.0},
                confidence=0.0,
                evidence_snr=ForensicEvidenceSummary(
                    geometry=0.0,
                    texture_silicone=0.0,
                    geometry_evidence_mode=GeometryEvidenceMode.UNAVAILABLE,
                ),
                flags=["QUALITY_REJECTED"],
                reasoning=[f"Quality gate rejected input photo(s): {', '.join(rejected)}"],
            )

        # C-01: Texture Analysis using face crops and UV textures if available
        crop_png_a = self.recon_root / photo_a.stem / "face_crop.png"
        crop_jpg_a = self.recon_root / photo_a.stem / "face_crop.jpg"
        crop_a = crop_png_a if crop_png_a.exists() else crop_jpg_a

        crop_png_b = self.recon_root / photo_b.stem / "face_crop.png"
        crop_jpg_b = self.recon_root / photo_b.stem / "face_crop.jpg"
        crop_b = crop_png_b if crop_png_b.exists() else crop_jpg_b

        uv_a = self.recon_root / photo_a.stem / "uv_texture_hd.jpg"
        uv_mask_a = self.recon_root / photo_a.stem / "uv_confidence_mask.jpg"
        uv_b = self.recon_root / photo_b.stem / "uv_texture_hd.jpg"
        uv_mask_b = self.recon_root / photo_b.stem / "uv_confidence_mask.jpg"
        
        target_a = crop_a if crop_a.exists() else photo_a
        target_b = crop_b if crop_b.exists() else photo_b
        
        tex_a = self.texture_analyzer.analyze_image(target_a, uv_path=uv_a, uv_mask_path=uv_mask_a)
        tex_b = self.texture_analyzer.analyze_image(target_b, uv_path=uv_b, uv_mask_path=uv_mask_b)
        
        # Calculate younger scores (1.0 - wrinkles) for Gate-0 (CH-01)
        y_a = 1.0 - float(tex_a.get("wrinkle_forehead", 0.0)) - float(tex_a.get("wrinkle_nasolabial", 0.0))
        y_b = 1.0 - float(tex_b.get("wrinkle_forehead", 0.0)) - float(tex_b.get("wrinkle_nasolabial", 0.0))
        
        # --- Stage 0: Temporal Gate ---
        chron_flags = self.chronology.check_pair_consistency(date_a, date_b, y_a=y_a, y_b=y_b)
        chron_flags.extend(self._collect_timeline_flags(timeline_context, date_a, date_b))

        # C-03: Use max() instead of mean() for silicone probability to preserve mask anomaly signal
        raw_silicone_a = float(tex_a.get("silicone_probability", 0.0))
        raw_silicone_b = float(tex_b.get("silicone_probability", 0.0))
        silicone_prob = max(raw_silicone_a, raw_silicone_b)
        
        # --- Stage 2: Deep Geometry ---
        recon_a = resolve_reconstruction(self.recon_adapter, photo_a, self.recon_root / photo_a.stem, neutral_expression=False)
        recon_b = resolve_reconstruction(self.recon_adapter, photo_b, self.recon_root / photo_b.stem, neutral_expression=False)
        
        comp_res = self.pair_engine.compare(recon_a, recon_b)
        if comp_res.status != "ok":
            diagnostics = comp_res.diagnostics or {}
            return ForensicVerdict(
                status=ForensicStatus.UNCERTAIN,
                fuzzy_label=FuzzyLabel.INSUFFICIENT_DATA,
                probabilities={"H0_same": 0.0, "H1_swap": 0.0, "H2_diff": 0.0},
                confidence=0.0,
                evidence_snr=ForensicEvidenceSummary(
                    geometry=0.0,
                    texture_silicone=silicone_prob,
                    geometry_evidence_mode=normalize_geometry_evidence_mode(
                        diagnostics.get("geometry_evidence_mode", GeometryEvidenceMode.UNAVAILABLE.value)
                    ),
                ),
                flags=[comp_res.status.upper()],
                reasoning=[
                    f"Pair comparison halted with status={comp_res.status}.",
                    f"Shared visible vertices={diagnostics.get('shared_visible_count', 0)}.",
                    "Final identity inference skipped because geometry evidence is insufficient.",
                ],
            )
        
        # --- Synthesis: Bayesian Verdict ---
        geom_snr = float(comp_res.diagnostics.get("geometry_snr", 0.0) or 0.0)
        geometry_evidence_mode = normalize_geometry_evidence_mode(
            comp_res.diagnostics.get("geometry_evidence_mode", GeometryEvidenceMode.FALLBACK.value)
        )
        
        verdict = self.verdict_engine.synthesize(
            geometry_snr=geom_snr,
            texture_silicone_prob=silicone_prob,
            chronology_flags=chron_flags,
            geometry_evidence_mode=geometry_evidence_mode,
        )
        
        return verdict

    def analyze_single(self, photo: Path) -> Dict[str, Any]:
        """
        Extracts a forensic passport for a single photo.
        """
        recon = resolve_reconstruction(self.recon_adapter, photo, self.recon_root / photo.stem, neutral_expression=False)
        
        # C-01: Pass face crop and UV if available
        crop_png_path = self.recon_root / photo.stem / "face_crop.png"
        crop_jpg_path = self.recon_root / photo.stem / "face_crop.jpg"
        crop_path = crop_png_path if crop_png_path.exists() else crop_jpg_path
        
        uv_path = self.recon_root / photo.stem / "uv_texture_hd.jpg"
        uv_mask_path = self.recon_root / photo.stem / "uv_confidence_mask.jpg"
        target_path = crop_path if crop_path.exists() else photo
        
        tex = self.texture_analyzer.analyze_image(target_path, uv_path=uv_path, uv_mask_path=uv_mask_path)
        quality = self.quality_gate.evaluate(photo)
        
        # C-02: Filter texture metrics based on pose bucket keys
        from core.utils import BUCKET_METRIC_KEYS, classify_pose_bucket
        bucket = classify_pose_bucket(recon.angles_deg[1])
        valid_keys = BUCKET_METRIC_KEYS.get(bucket, set())
        filtered_tex = {k: v for k, v in tex.items() if k in valid_keys or k == "quality"}
        
        return {
            "photo_id": photo.stem,
            "quality": quality,
            "texture": filtered_tex,
            "reconstruction_summary": {
                "vertex_count": len(recon.vertices_world),
                "pose": recon.angles_deg.tolist()
            }
        }

