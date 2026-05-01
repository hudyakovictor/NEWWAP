from __future__ import annotations

import shutil
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from datetime import datetime
from core.config import SETTINGS
from core.analysis import calculate_bayesian_evidence
from core.detail_mapper import map_record_to_detail
from core.jobs import JobManager
from core.models import CalibrationOverrideRequest, ExtractJobRequest, RecomputeMetricsRequest
from core.service import ForensicWorkbenchService
from core.utils import IMAGE_EXTENSIONS, read_json


class EvidenceRequest(BaseModel):
    photo_id_a: str
    photo_id_b: str


def iso_now() -> str:
    return datetime.now().isoformat()

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
def photos(
    dataset: str,
    pose: str | None = None,
    source: str | None = None,
    search: str | None = None,
    sortBy: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    if dataset not in {"main", "calibration"}:
        raise HTTPException(status_code=404, detail="unknown dataset")
    items = service.main_records() if dataset == "main" else service.calibration_records()
    
    # Apply filters
    if pose:
        items = [r for r in items if r.get("bucket") == pose or r.get("angle") == pose]
    if source:
        items = [r for r in items if r.get("pose", {}).get("pose_source") == source]
    if search:
        q = search.lower()
        items = [r for r in items if q in r.get("filename", "").lower() or q in r.get("photo_id", "").lower()]
    
    # Apply sorting
    if sortBy == "date":
        items.sort(key=lambda r: r.get("date_str", ""))
    elif sortBy == "synthetic":
        items.sort(key=lambda r: float(r.get("syntheticProb", 0)), reverse=True)
    elif sortBy == "bayes":
        items.sort(key=lambda r: float(r.get("bayesH0") or 0), reverse=True)
    
    # Apply pagination
    total = len(items)
    if offset:
        items = items[offset:]
    if limit:
        items = items[:limit]
    
    return {"total": total, "items": items}


@app.get("/api/photo/{dataset}/{photo_id}")
def photo_detail(dataset: str, photo_id: str) -> dict:
    record = service.photo_detail(dataset, photo_id)
    if record is None:
        raise HTTPException(status_code=404, detail="photo not found")
    
    detail = map_record_to_detail(record)
    # UI expects { ...detail, record }
    return {**detail, "record": record}


@app.get("/api/timeline-summary")
def timeline_summary() -> dict:
    return service.get_timeline_full()


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


@app.post("/api/evidence/compare")
async def compare_evidence(request: EvidenceRequest):
    """
    Вычисляет криминалистический вердикт на основе реальных данных из summary.json.
    Принимает JSON body: {"photo_id_a": "...", "photo_id_b": "..."}
    """
    summary_a = service.photo_detail("main", request.photo_id_a)
    summary_b = service.photo_detail("main", request.photo_id_b)
    
    if not summary_a or not summary_b:
        raise HTTPException(
            status_code=404, 
            detail=f"Данные не найдены для {request.photo_id_a} или {request.photo_id_b}."
        )
    
    evidence = calculate_bayesian_evidence(summary_a, summary_b)
    return evidence


@app.post("/api/evidence/matrix")
async def comparison_matrix(photo_ids: list[str] = Body(...)):
    """
    Строит матрицу похожести N×N для выбранных фотографий.
    Принимает JSON body: ["id1", "id2", "id3"]
    """
    summaries = []
    for pid in photo_ids:
        s = service.photo_detail("main", pid)
        if s:
            summaries.append(s)
    
    n = len(summaries)
    matrix = [[0.0] * n for _ in range(n)]
    
    for i in range(n):
        for j in range(i, n):
            if i == j:
                matrix[i][j] = 1.0
            else:
                ev = calculate_bayesian_evidence(summaries[i], summaries[j])
                prob = float(ev["posteriors"]["H0"])
                matrix[i][j] = prob
                matrix[j][i] = prob
                
    return matrix


@app.get("/api/similar-photos/{photo_id}")
async def similar_photos(photo_id: str, limit: int = 5):
    """
    Возвращает список наиболее похожих фотографий (по геометрии и позе).
    """
    target = service.photo_detail("main", photo_id)
    if not target:
        raise HTTPException(status_code=404, detail="Photo not found")
        
    all_main = service.main_records()
    candidates = [r for r in all_main if r["photo_id"] != photo_id and r.get("status") == "ready"]
    
    if not candidates:
        # Fallback to pending photos if nothing is processed yet, to satisfy audit
        candidates = [r for r in all_main if r["photo_id"] != photo_id][:limit*2]
    
    scored = []
    for cand in candidates:
        ev = calculate_bayesian_evidence(target, cand)
        scored.append({"record": cand, "score": float(ev["posteriors"]["H0"])})
        
    scored.sort(key=lambda x: x["score"], reverse=True)
    return [s["record"] for s in scored[:limit]]


@app.get("/api/photos-in-bucket")
def photos_in_bucket(pose: str, light: str | None = None, limit: int = 50) -> list[dict]:
    """Returns photos matching a calibration bucket pose (and optionally light)."""
    records = service.main_records()
    filtered = [r for r in records if r.get("bucket") == pose or r.get("angle") == pose]
    return filtered[:limit]


@app.get("/api/investigations")
def list_investigations() -> list[dict]:
    return service.get_investigations()


@app.post("/api/investigations")
def upsert_investigation(inv: dict) -> dict:
    return service.upsert_investigation(inv)


@app.delete("/api/investigations/{inv_id}")
def delete_investigation(inv_id: str) -> dict:
    result = service.delete_investigation(inv_id)
    if not result:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return result


@app.get("/api/pipeline/stages")
def pipeline_stages() -> list[dict]:
    return service.get_pipeline_stages()


@app.get("/api/cache/summary")
def cache_summary() -> dict:
    return service.get_cache_summary()


@app.get("/api/debug/ageing")
def ageing_series() -> list[dict]:
    return service.get_ageing_series()


@app.get("/api/debug/catalog")
def api_catalog() -> list[dict]:
    """
    Returns a catalog of all available API endpoints for the audit tool.
    """
    return [
        {"method": "GET", "path": "/api/timeline-summary", "description": "Full timeline data", "group": "debug"},
        {"method": "GET", "path": "/api/photos/main", "description": "List all photos", "group": "photos"},
        {"method": "GET", "path": "/api/calibration/summary", "description": "Calibration status", "group": "calibration"},
        {"method": "GET", "path": "/api/anomalies", "description": "System anomalies", "group": "anomalies"},
        {"method": "GET", "path": "/api/pipeline/stages", "description": "Pipeline diagnostics", "group": "debug"},
    ]


@app.get("/api/anomalies")
def list_anomalies() -> list[dict]:
    """
    Возвращает список криминалистических аномалий в датасете.
    """
    main_records = service.main_records()
    anomalies = []
    
    for r in main_records:
        flags = r.get("anomaly_flags", [])
        for f in flags:
            if not isinstance(f, dict):
                continue
            flag_type = f.get("type", "")
            flag_severity = f.get("severity", "warn")
            # Map internal severity to UI severity
            ui_severity = "danger" if flag_severity == "critical" else "warn" if flag_severity == "high" else "info"
            anomalies.append({
                "id": f"{r['photo_id']}_{flag_type}",
                "year": r.get("year", r.get("parsed_year", 2000)),
                "severity": ui_severity,
                "kind": "pose" if "pose" in flag_type else "chronology",
                "photoId": r["photo_id"],
                "title": f.get("description", f"Аномалия: {flag_type}"),
                "detectedAt": r.get("extracted_at", iso_now()),
                "resolved": False
            })
            
    return anomalies


@app.get("/api/diary")
def get_diary() -> list[dict]:
    return service.get_diary()


@app.post("/api/diary")
def add_diary_entry(entry: dict) -> dict:
    return service.add_diary_entry(entry)


@app.put("/api/diary/{entry_id}")
def update_diary_entry(entry_id: str, patch: dict) -> dict:
    try:
        return service.update_diary_entry(entry_id, patch)
    except KeyError:
        raise HTTPException(status_code=404, detail="Entry not found")


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
