from __future__ import annotations

import shutil
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.config import SETTINGS
from core.jobs import JobManager
from core.models import CalibrationOverrideRequest, ExtractJobRequest, RecomputeMetricsRequest
from core.service import ForensicWorkbenchService
from core.utils import IMAGE_EXTENSIONS

service = ForensicWorkbenchService()
jobs = JobManager()
UI_DIST_DIR = SETTINGS.newapp_root / "ui" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    tunnel = None
    if SETTINGS.localxpose_token:
        try:
            tunnel = subprocess.Popen(
                ["loclx", "tunnel", "http", "--to", f"localhost:{SETTINGS.port}", "--auth", SETTINGS.localxpose_token],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            tunnel = None
    yield
    if tunnel is not None:
        tunnel.terminate()


app = FastAPI(title="Dutin NewApp", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/storage", StaticFiles(directory=str(SETTINGS.storage_root)), name="storage")
app.mount("/source/main", StaticFiles(directory=str(SETTINGS.main_photos_dir)), name="source-main")
app.mount("/source/calibration", StaticFiles(directory=str(SETTINGS.calibration_dir)), name="source-calibration")
if (UI_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(UI_DIST_DIR / "assets")), name="ui-assets")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/overview")
def overview() -> dict:
    return service.overview()


@app.get("/api/photos/{dataset}")
def photos(dataset: str) -> list[dict]:
    if dataset not in {"main", "calibration"}:
        raise HTTPException(status_code=404, detail="unknown dataset")
    return service.main_records() if dataset == "main" else service.calibration_records()


@app.get("/api/photo/{dataset}/{photo_id}")
def photo_detail(dataset: str, photo_id: str) -> dict:
    record = service.photo_detail(dataset, photo_id)
    if record is None:
        raise HTTPException(status_code=404, detail="photo not found")
    return record


@app.get("/api/timeline-summary")
def timeline_summary() -> dict:
    return service.overview()["timeline_summary"]


@app.get("/api/calibration/summary")
def calibration_summary() -> dict:
    return service.calibration_summary()


@app.get("/api/recommendations")
def recommendations() -> list[dict]:
    return service.recommendations()


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return jobs.list_jobs()


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    data = jobs.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="job not found")
    return data


@app.post("/api/jobs/extract")
def start_extract(request: ExtractJobRequest) -> dict:
    job_id = jobs.start(
        "extract",
        request.dataset,
        lambda progress: service.process_dataset(
            request.dataset,
            limit=request.limit,
            only_ids=request.only_ids,
            progress_callback=progress,
        ),
    )
    return {"job_id": job_id}


@app.post("/api/jobs/recompute-metrics")
def start_recompute_metrics(request: RecomputeMetricsRequest) -> dict:
    job_id = jobs.start(
        "recompute-metrics",
        request.dataset,
        lambda progress: service.recompute_metrics(
            request.dataset,
            metric_keys=request.metric_keys,
            only_ids=request.only_ids,
            progress_callback=progress,
        ),
    )
    return {"job_id": job_id}


@app.post("/api/calibration/override")
def set_override(request: CalibrationOverrideRequest) -> dict:
    return service.set_calibration_override(request.photo_id, request.calibration_photo_id)


@app.post("/api/upload")
async def upload_photo(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    dest = SETTINGS.main_photos_dir / file.filename
    # Avoid overwriting — add suffix if needed
    counter = 1
    while dest.exists():
        stem = Path(file.filename).stem
        dest = SETTINGS.main_photos_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    content = await file.read()
    dest.write_bytes(content)
    # Build stub to return bucket/pose info
    stub = service._build_stub("main", dest)
    return {
        "filename": dest.name,
        "photo_id": stub["photo_id"],
        "bucket": stub["bucket"],
        "pose": stub["pose"],
        "status": stub["status"],
    }


@app.post("/api/reset-all")
def reset_all() -> dict:
    """Reset derived storage only. Source photos are NEVER deleted."""
    main_storage = SETTINGS.storage_root / "main"
    removed = 0
    if main_storage.exists():
        for item in main_storage.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
                removed += 1
    return {"status": "ok", "removed_storage_dirs": removed}


@app.delete("/api/photo/{dataset}/{photo_id}")
def delete_photo(dataset: str, photo_id: str) -> dict:
    """Delete derived storage for a photo. Source file is kept."""
    if dataset not in {"main", "calibration"}:
        raise HTTPException(status_code=404, detail="unknown dataset")
    storage_dir = SETTINGS.storage_root / dataset / photo_id
    if storage_dir.exists():
        shutil.rmtree(storage_dir)
        return {"status": "ok", "photo_id": photo_id}
    raise HTTPException(status_code=404, detail="no derived data for this photo")


@app.get("/")
def root() -> FileResponse:
    dist_index = UI_DIST_DIR / "index.html"
    if dist_index.exists():
        return FileResponse(dist_index)
    readme = SETTINGS.newapp_root / "README.md"
    if readme.exists():
        return FileResponse(readme)
    raise HTTPException(status_code=404, detail="UI not built yet")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str) -> FileResponse:
    dist_index = UI_DIST_DIR / "index.html"
    if dist_index.exists():
        return FileResponse(dist_index)
    readme = SETTINGS.newapp_root / "README.md"
    if readme.exists():
        return FileResponse(readme)
    raise HTTPException(status_code=404, detail=f"Path not found: {full_path}")
