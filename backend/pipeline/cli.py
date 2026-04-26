from __future__ import annotations

import argparse
import json
from pathlib import Path

from typing import Optional
from .cascade import CascadeEngine
from core.utils import json_ready

def main():
    parser = argparse.ArgumentParser(description="Forensic Pipeline CLI (Iteration 4)")
    parser.add_argument("image_a", type=Path, help="Path to first image")
    parser.add_argument("image_b", type=Optional[Path], default=None, help="Path to second image (optional, triggers comparison)")
    parser.add_argument("--output", type=Path, default=Path("forensic_result.json"), help="Output JSON path")
    
    args = parser.parse_args()
    
    cascade = CascadeEngine()
    
    if args.image_b:
        print(f"[*] Running Pairwise Forensic Analysis: {args.image_a.name} vs {args.image_b.name}")
        # In Iteration 4, we'd call a compare method on CascadeEngine
        # For now, we demonstrate the single analysis flow
        passport_a = cascade.analyze_single(args.image_a)
        passport_b = cascade.analyze_single(args.image_b)
        
        result = {
            "passport_a": passport_a,
            "passport_b": passport_b,
            "verdict": "demonstration_mode"
        }
    else:
        print(f"[*] Running Single Forensic Passport Extraction: {args.image_a.name}")
        result = cascade.analyze_single(args.image_a)
        
    args.output.write_text(json.dumps(json_ready(result), indent=2), encoding="utf-8")
    print(f"[+] Result saved to {args.output}")

if __name__ == "__main__":
    main()
