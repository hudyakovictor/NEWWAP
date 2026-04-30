import os
import sys
import json
import hashlib
from pathlib import Path
from PIL import Image
from datetime import datetime

# Add backend to sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from pipeline.cascade import CascadeEngine
from core.utils import json_ready

def compute_md5(path: Path):
    hasher = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def get_resolution(path: Path):
    with Image.open(path) as img:
        return f"{img.width}x{img.height}"

def process_photos(photo_paths, output_dir: Path, progress_file: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load progress
    if progress_file.exists():
        with open(progress_file, 'r') as f:
            processed = set(json.load(f))
    else:
        processed = set()

    cascade = CascadeEngine()
    
    results = {}
    
    try:
        for i, path in enumerate(photo_paths):
            photo_id = path.name
            if photo_id in processed:
                print(f"[{i+1}/{len(photo_paths)}] Skipping {photo_id} (already processed)")
                continue
                
            print(f"[{i+1}/{len(photo_paths)}] Processing {photo_id}...")
            try:
                passport = cascade.analyze_single(path)
                
                # Add extra fields for the UI
                passport["md5"] = compute_md5(path)
                passport["resolution"] = get_resolution(path)
                passport["source"] = "real_dataset"
                
                # Extract syntheticProb from texture analysis
                # texture analyzer returns 'silicone_probability'
                passport["syntheticProb"] = passport.get("texture", {}).get("silicone_probability", 0.0)
                
                # Save individual result
                result_path = output_dir / f"{path.stem}.json"
                with open(result_path, 'w') as f:
                    json.dump(json_ready(passport), f, indent=2)
                
                processed.add(photo_id)
                
                # Save progress periodically
                if len(processed) % 5 == 0:
                    with open(progress_file, 'w') as f:
                        json.dump(list(processed), f)
                        
            except Exception as e:
                import traceback
                print(f"Error processing {photo_id}: {e}")
                traceback.print_exc()
                # Don't stop the whole process, just log the error
                
    finally:
        # Final progress save
        with open(progress_file, 'w') as f:
            json.dump(list(processed), f)

def main():
    # Small sample for testing
    main_dir = Path("/Users/victorkhudyakov/dutin/newapp/ui/public/photos_main")
    myface_dir = Path("/Users/victorkhudyakov/dutin/newapp/ui/public/photos_myface")
    
    sample_photos = []
    
    # Take first 3 from each
    if main_dir.exists():
        sample_photos.extend(sorted(list(main_dir.glob("*.jpg")))[:3])
    if myface_dir.exists():
        sample_photos.extend(sorted(list(myface_dir.glob("*.jpg")))[:3])
        sample_photos.extend(sorted(list(myface_dir.glob("*.png")))[:2])
        
    print(f"Found {len(sample_photos)} photos for sample run")
    
    output_dir = REPO_ROOT / "storage" / "forensic_passports"
    progress_file = REPO_ROOT / "storage" / "extraction_progress.json"
    
    process_photos(sample_photos, output_dir, progress_file)

if __name__ == "__main__":
    main()
