import os
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PASSPORT_DIR = REPO_ROOT / "storage" / "forensic_passports"
OUTPUT_FILE = REPO_ROOT / "ui" / "src" / "data" / "forensic_registry.json"

def consolidate():
    registry = {}
    if not PASSPORT_DIR.exists():
        print(f"Directory {PASSPORT_DIR} does not exist")
        return

    for path in PASSPORT_DIR.glob("*.json"):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                registry[data["photo_id"]] = data
        except Exception as e:
            print(f"Error loading {path.name}: {e}")

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(registry, f, indent=2)
    print(f"Consolidated {len(registry)} passports to {OUTPUT_FILE}")

if __name__ == "__main__":
    consolidate()
