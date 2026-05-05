#!/usr/bin/env python3
from pathlib import Path
from PIL import Image

SOURCE_DIR = Path("/Volumes/SDCARD/photo/calibration")
MAX_SIZE = 1200

exts = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
files = [f for f in SOURCE_DIR.iterdir() if f.is_file() and f.suffix in exts]
print(f"Found {len(files)} images")

to_resize = []
for img_path in files:
    try:
        with Image.open(img_path) as img:
            w, h = img.size
            if w > MAX_SIZE or h > MAX_SIZE:
                to_resize.append((img_path, w, h))
    except Exception as e:
        print(f"  Error: {img_path.name}: {e}")

if not to_resize:
    print("No images need resizing (all <= 1200px).")
else:
    print(f"\nFound {len(to_resize)} images to resize:")
    for path, w, h in to_resize:
        print(f"  {w}x{h} | {path.name}")
    
    print("\nResizing with Lanczos, quality=95...")
    for img_path, ow, oh in to_resize:
        try:
            with Image.open(img_path) as img:
                ratio = min(MAX_SIZE / ow, MAX_SIZE / oh)
                nw, nh = int(ow * ratio), int(oh * ratio)
                resized = img.resize((nw, nh), Image.LANCZOS)
                exif = img.info.get('exif')
                kwargs = {'quality': 95, 'optimize': True}
                if exif:
                    kwargs['exif'] = exif
                resized.save(img_path, **kwargs)
                print(f"  {ow}x{oh} -> {nw}x{nh} | {img_path.name}")
        except Exception as e:
            print(f"  ERROR: {img_path.name}: {e}")
    
    print(f"\nDone. Resized {len(to_resize)} images.")