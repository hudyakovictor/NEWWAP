from __future__ import annotations

import numpy as np
from enum import Enum
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from core.constants import PRIOR_SAME_PERSON, SNR_SIGNAL_THRESHOLD, SNR_UNCERTAIN_THRESHOLD

def _clamp01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))

class ForensicStatus(Enum):
    SAME_PERSON = "same_person"
    UNCERTAIN = "uncertain"
    DIFFERENT_PERSON = "different_person"
    IDENTITY_SWAP = "identity_swap" 
    RETURN_TO_BASELINE = "return_to_baseline"

class GeometryEvidenceMode(Enum):
    CALIBRATED = "calibrated"
    FALLBACK = "fallback"
    UNAVAILABLE = "unavailable"

class FuzzyLabel(Enum):
    STRONGLY_MATCHING = "strongly_matching"
    CONSISTENT = "consistent"
    INSUFFICIENT_DATA = "insufficient_data"
    WEAK_EVIDENCE = "weak_evidence"
    SUSPICIOUS_TEXTURE = "suspicious_texture"
    GEOMETRIC_MISMATCH = "geometric_mismatch"
    IDENTITY_ANOMALY = "identity_anomaly"
    TEMPORAL_IMPOSSIBILITY = "temporal_impossibility"

@dataclass
class ForensicEvidenceSummary:
    geometry: float
    texture_silicone: float
    geometry_evidence_mode: GeometryEvidenceMode

@dataclass
class ForensicVerdict:
    status: ForensicStatus
    fuzzy_label: FuzzyLabel
    probabilities: Dict[str, float] # P(H0), P(H1), P(H2)
    confidence: float
    evidence_snr: ForensicEvidenceSummary
    flags: List[str] = field(default_factory=list)
    reasoning: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["fuzzy_label"] = self.fuzzy_label.value
        d["evidence_snr"]["geometry_evidence_mode"] = self.evidence_snr.geometry_evidence_mode.value
        return d

def normalize_geometry_evidence_mode(value: GeometryEvidenceMode | str | None) -> GeometryEvidenceMode:
    if isinstance(value, GeometryEvidenceMode):
        return value
    try:
        return GeometryEvidenceMode(str(value or GeometryEvidenceMode.UNAVAILABLE.value))
    except ValueError:
        return GeometryEvidenceMode.UNAVAILABLE


def _attenuate_likelihood(likelihood: float, alpha: float) -> float:
    alpha = float(min(1.0, max(0.0, alpha)))
    return float(1.0 + alpha * (float(likelihood) - 1.0))


class BayesianMultiHypothesisEngine:
    """
    [ITER-4] Bayesian-Fuzzy Multi-Hypothesis Engine.
    Hypotheses:
    - H0: Same Person (Natural consistency)
    - H1: Identity Swap (Silicon, Mask, Deepfake)
    - H2: Different Person (Natural variation)
    """
    def __init__(self):
        h2_prior = max(0.0, 1.0 - PRIOR_SAME_PERSON - 0.05)
        self.priors = {
            "H0": PRIOR_SAME_PERSON,      # Same
            "H1": 0.05,                  # Swap/Mask (Rare but critical)
            "H2": h2_prior               # Different (guarded against negative)
        }

    def synthesize(
        self, 
        geometry_snr: float, 
        texture_silicone_prob: float, 
        chronology_flags: List[Dict[str, Any]],
        geometry_evidence_mode: GeometryEvidenceMode | str = GeometryEvidenceMode.CALIBRATED,
    ) -> ForensicVerdict:
        """
        Bayesian synthesis of evidence across three hypotheses.
        """
        # 1. Input normalization + evidence-policy selection
        snr = float(max(geometry_snr, 0.0))
        tex = _clamp01(texture_silicone_prob)
        geometry_evidence_mode = normalize_geometry_evidence_mode(geometry_evidence_mode)

        if geometry_evidence_mode == GeometryEvidenceMode.CALIBRATED:
            geom_alpha = 1.0
            confidence_cap: Optional[float] = None
            allow_hard_identity = True
            geometry_flag: Optional[str] = None
            geometry_channel_enabled = True
        elif geometry_evidence_mode == GeometryEvidenceMode.FALLBACK:
            geom_alpha = 0.45
            confidence_cap = 0.75
            allow_hard_identity = False
            geometry_flag = "FALLBACK_GEOMETRY"
            geometry_channel_enabled = True
        else:
            geom_alpha = 0.0
            confidence_cap = 0.50
            allow_hard_identity = False
            geometry_flag = "GEOMETRY_UNAVAILABLE"
            geometry_channel_enabled = False

        # Geometry evidence:
        # - H0 peaks at low SNR and decays quickly after the uncertain band.
        # - H2 grows as geometry rises above the calibrated signal threshold.
        # - H1 is strongest when geometry is elevated but not maximally different,
        #   because a mask / swap may preserve part of the canonical structure.
        raw_l_geom_h0 = float(np.exp(-0.5 * (snr / max(SNR_UNCERTAIN_THRESHOLD, 1e-6)) ** 2))
        raw_l_geom_h2 = _sigmoid((snr - SNR_SIGNAL_THRESHOLD) * 2.0)
        raw_l_geom_h1 = float(np.exp(-0.5 * ((snr - SNR_SIGNAL_THRESHOLD) / 1.25) ** 2))

        l_geom_h0 = _attenuate_likelihood(raw_l_geom_h0, geom_alpha)
        l_geom_h1 = _attenuate_likelihood(raw_l_geom_h1, geom_alpha)
        l_geom_h2 = _attenuate_likelihood(raw_l_geom_h2, geom_alpha)

        # Texture evidence:
        # - H1 increases with silicone probability.
        # - H0 tolerates only low synthetic probability.
        # - H2 should not be penalized as aggressively by texture alone because
        #   different people can still have natural skin statistics.
        l_tex_h1 = max(tex, 1e-3)
        l_tex_h0 = max(1.0 - tex, 1e-3)
        l_tex_h2 = max(0.35, 1.0 - tex * 0.5)

        # Chronology evidence as multiplicative gates.
        chrono_h0 = 1.0
        chrono_h1 = 1.0
        chrono_h2 = 1.0
        impossible_prior = 0.0
        for flag in chronology_flags:
            flag_type = str(flag.get("type", ""))
            prior_p = float(flag.get("prior_p", 0.0) or 0.0)
            impossible_prior = max(impossible_prior, prior_p)
            if flag_type == "impossible_short":
                chrono_h0 *= 0.05
                chrono_h1 *= 1.0 + max(0.5, prior_p)
                chrono_h2 *= 0.60
            elif flag_type == "return":  # chronology.py generates type="return"
                chrono_h0 *= 0.15
                chrono_h1 *= 1.75
                chrono_h2 *= 0.75
            elif flag_type == "transition":  # chronology.py generates type="transition"
                chrono_h0 *= 0.60
                chrono_h1 *= 1.15
                chrono_h2 *= 1.20

        # 2. Update Priors
        p_h0 = self.priors["H0"] * l_geom_h0 * l_tex_h0 * chrono_h0
        p_h1 = self.priors["H1"] * l_geom_h1 * l_tex_h1 * chrono_h1
        p_h2 = self.priors["H2"] * l_geom_h2 * l_tex_h2 * chrono_h2
        
        # Normalize
        total = p_h0 + p_h1 + p_h2 + 1e-9
        p_h0 /= total
        p_h1 /= total
        p_h2 /= total
        
        probs = {"H0_same": float(p_h0), "H1_swap": float(p_h1), "H2_diff": float(p_h2)}
        
        # 3. Deterministic chronology gates + provenance flags
        flags = []
        reasoning = []
        is_impossible = any(f["type"] == "impossible_short" for f in chronology_flags)
        is_rtr = any(f["type"] == "return" for f in chronology_flags)  # chronology.py uses "return"

        if is_impossible:
            flags.append("TEMPORAL_IMPOSSIBILITY")
        if is_rtr:
            flags.append("RETURN_TO_BASELINE")
        if geometry_flag:
            flags.append(geometry_flag)

        # 4. Candidate verdict from posterior
        if is_impossible or p_h1 > 0.60:
            status = ForensicStatus.IDENTITY_SWAP
            label = FuzzyLabel.IDENTITY_ANOMALY
            confidence = max(p_h1, max(0.90, impossible_prior)) if is_impossible else p_h1
        elif is_rtr:
            status = ForensicStatus.RETURN_TO_BASELINE
            label = FuzzyLabel.IDENTITY_ANOMALY
            confidence = max(0.85, p_h1)
        elif geometry_channel_enabled and p_h0 > 0.80 and snr <= SNR_UNCERTAIN_THRESHOLD and tex < 0.35:
            status = ForensicStatus.SAME_PERSON
            label = FuzzyLabel.STRONGLY_MATCHING
            confidence = p_h0
        elif geometry_channel_enabled and p_h2 > 0.75 and snr >= SNR_SIGNAL_THRESHOLD:
            status = ForensicStatus.DIFFERENT_PERSON
            label = FuzzyLabel.GEOMETRIC_MISMATCH
            confidence = p_h2
        elif p_h1 > 0.30 or tex > 0.50:
            status = ForensicStatus.UNCERTAIN
            label = FuzzyLabel.SUSPICIOUS_TEXTURE
            confidence = max(p_h1, tex)
        else:
            status = ForensicStatus.UNCERTAIN
            label = FuzzyLabel.CONSISTENT
            confidence = max(p_h0, p_h2, 0.5)

        # 5. Provenance policy enforcement
        if not allow_hard_identity and status in {ForensicStatus.SAME_PERSON, ForensicStatus.DIFFERENT_PERSON}:
            status = ForensicStatus.UNCERTAIN
            label = FuzzyLabel.WEAK_EVIDENCE if geometry_evidence_mode == GeometryEvidenceMode.FALLBACK else FuzzyLabel.INSUFFICIENT_DATA
        elif geometry_evidence_mode == GeometryEvidenceMode.FALLBACK and status == ForensicStatus.UNCERTAIN and label == FuzzyLabel.CONSISTENT:
            label = FuzzyLabel.WEAK_EVIDENCE
        elif geometry_evidence_mode == GeometryEvidenceMode.UNAVAILABLE and status == ForensicStatus.UNCERTAIN and label == FuzzyLabel.CONSISTENT:
            label = FuzzyLabel.INSUFFICIENT_DATA

        if confidence_cap is not None:
            confidence = min(float(confidence), confidence_cap)

        # [SYS-05] Always clamp confidence to [0, 1]
        confidence = _clamp01(float(confidence))

        # Reasoning
        reasoning.append(f"Bayesian Posterior: Same={p_h0:.2f}, Swap/Mask={p_h1:.2f}, Diff={p_h2:.2f}")
        geometry_mode = geometry_evidence_mode
        if geometry_mode == GeometryEvidenceMode.CALIBRATED:
            reasoning.append(f"Geometry evidence interpreted as {geometry_mode.value}; the geometry channel contributed fully with SNR={snr:.2f}.")
        elif geometry_mode == GeometryEvidenceMode.FALLBACK:
            reasoning.append(f"Geometry evidence interpreted as {geometry_mode.value}; the geometry channel was attenuated before posterior synthesis with raw SNR={snr:.2f}.")
        else:
            reasoning.append(f"Geometry evidence interpreted as {geometry_mode.value}; the geometry channel was disabled during posterior synthesis and raw SNR={snr:.2f} is retained only for traceability.")

        if geometry_channel_enabled and snr > SNR_SIGNAL_THRESHOLD:
            reasoning.append(f"Significant geometric deviation detected (SNR={snr:.2f}).")
        elif geometry_channel_enabled and snr <= SNR_UNCERTAIN_THRESHOLD:
            reasoning.append(f"Geometry remains within the expected natural-variation band (SNR={snr:.2f}).")
        if tex > 0.5:
            reasoning.append(f"Texture analysis indicates synthetic materials (P={tex:.2f}).")
        if geometry_mode == GeometryEvidenceMode.FALLBACK:
            reasoning.append("Hard identity conclusions were downgraded because geometry came from a fallback proxy rather than a calibrated noise model.")
        elif geometry_mode == GeometryEvidenceMode.UNAVAILABLE:
            reasoning.append("Hard identity conclusions were disabled because a usable geometry channel could not be established.")
        if confidence_cap is not None:
            reasoning.append(f"Confidence was capped at {confidence_cap:.2f} by the geometry evidence policy.")

        return ForensicVerdict(
            status=status,
            fuzzy_label=label,
            probabilities=probs,
            confidence=float(confidence),
            evidence_snr=ForensicEvidenceSummary(
                geometry=snr,
                texture_silicone=tex,
                geometry_evidence_mode=geometry_mode,
            ),
            flags=flags,
            reasoning=reasoning
        )
