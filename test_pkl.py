import pickle
from pathlib import Path

recon_path = Path("/Volumes/SDCARD/storage/main/2010_04_03_y65p-1r-4/reconstruction_v1.pkl")
if recon_path.exists():
    with open(recon_path, "rb") as f:
        recon = pickle.load(f)
    print(recon["result"].angles_deg)
else:
    print("Not extracted yet")
