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

        # Texture Analysis
        tex_a = self.texture_analyzer.analyze_image(photo_a)
        tex_b = self.texture_analyzer.analyze_image(photo_b)
        # [FIX-70] Взвешенное среднее вместо max() — не усиливаем шум одного фото
        raw_silicone_a = float(tex_a.get("silicone_probability", 0.0))
        raw_silicone_b = float(tex_b.get("silicone_probability", 0.0))
        silicone_prob = (raw_silicone_a + raw_silicone_b) / 2.0
        
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
        tex = self.texture_analyzer.analyze_image(photo)
        quality = self.quality_gate.evaluate(photo)
        
        return {
            "photo_id": photo.stem,
            "quality": quality,
            "texture": tex,
            "reconstruction_summary": {
                "vertex_count": len(recon.vertices_world),
                "pose": recon.angles_deg.tolist()
            }
        }
