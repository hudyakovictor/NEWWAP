#!/usr/bin/env python3
import os
from pathlib import Path

STORAGE_ROOT = Path(__file__).resolve().parents[1] / "storage"

def cleanup_artifacts():
    print(f"Cleaning up temporary artifacts in {STORAGE_ROOT}...")
    count = 0
    for p in STORAGE_ROOT.rglob("*.tmp"):
        try:
            p.unlink()
            count += 1
        except Exception as e:
            print(f"Failed to delete {p}: {e}")
            
    for p in STORAGE_ROOT.rglob("*.pkl.tmp"):
        try:
            p.unlink()
            count += 1
        except Exception as e:
            print(f"Failed to delete {p}: {e}")
            
    print(f"Done. Removed {count} temporary files.")

if __name__ == "__main__":
    cleanup_artifacts()
