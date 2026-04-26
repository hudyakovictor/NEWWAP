from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from .cascade import CascadeEngine
from .types import ReconstructionResult
from core.utils import iso_now, json_ready
from .constants import ARTIFACT_VERSION

class ForensicBatchProcessor:
    """
    [ITER-5] Forensic Batch Processor.
    Orchestrates the analysis of multiple photos into a unified forensic report.
    """
    def __init__(self, cascade: Optional[CascadeEngine] = None):
        self.cascade = cascade or CascadeEngine()

    def process_directory(
        self, 
        input_dir: Path, 
        output_dir: Path,
        reference_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes all images in a directory and builds a forensic bundle.
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        image_paths = sorted([
            p for p in input_dir.iterdir() 
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ])

        results = []
        for img_path in image_paths:
            try:
                # We assume metadata (date) is extracted from filename or sidecar for now
                # In a real system, this would be more robust.
                photo_id = img_path.stem
                
                # Run Cascade Analysis
                passport = self.cascade.analyze_single(img_path)
                
                results.append(passport)
                
                # Save individual passport
                passport_path = output_dir / f"{photo_id}_passport.json"
                passport_path.write_text(json.dumps(json_ready(passport), indent=2), encoding="utf-8")
                
            except Exception as e:
                print(f"Error processing {img_path.name}: {e}")

        # Build Bundle Summary
        bundle = {
            "version": ARTIFACT_VERSION,
            "generated_at": iso_now(),
            "input_directory": str(input_dir),
            "photo_count": len(results),
            "passports": results
        }
        
        bundle_path = output_dir / "forensic_bundle.json"
        bundle_path.write_text(json.dumps(json_ready(bundle), indent=2), encoding="utf-8")
        
        return bundle
