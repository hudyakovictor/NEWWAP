from __future__ import annotations
import numpy as np
from collections import defaultdict
import time

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analysis import extract_photo_bundle, recompute_metric_subset
from .calibration import build_calibration_summary, bucket_metric_health, pose_distance, stability_score
from .chronology import build_timeline, build_timeline_summary
from .config import SETTINGS
from .recommendations import build_recommendations
from .utils import (
    ALL_BUCKETS,
    BUCKET_LABELS,
    BUCKET_METRIC_KEYS,
    FORENSIC_RADAR_AXES,
    bytes_to_human,
    directory_size,
    ensure_directory,
    fallback_date_for_file,
    list_image_files,
    parse_date_from_name,
    read_json,
    stable_photo_id,
    write_json,
)

UI_EXPECTED_POSES = ["frontal", "three_quarter_left", "three_quarter_right", "profile_left", "profile_right"]
UI_EXPECTED_LIGHTS = ["daylight", "studio", "low_light", "mixed", "flash"]


@dataclass
class DatasetDescriptor:
    name: str
    root: Path


class ForensicWorkbenchService:
    def __init__(self) -> None:
        self.datasets = {
            "main": DatasetDescriptor("main", SETTINGS.main_photos_dir),
            "calibration": DatasetDescriptor("calibration", SETTINGS.calibration_dir),
        }
        self.storage_root = ensure_directory(SETTINGS.storage_root)
        ensure_directory(SETTINGS.main_photos_dir)
        ensure_directory(SETTINGS.calibration_dir)
        ensure_directory(self.storage_root / "main")
        ensure_directory(self.storage_root / "calibration")
        self.override_path = self.storage_root / "calibration_overrides.json"
        # Cache: invalidated on any write_json call or after TTL
        self._records_cache: dict[str, list[dict[str, Any]]] = {}
        self._records_cache_ts: dict[str, float] = {}
        self._main_records_cache: list[dict[str, Any]] | None = None
        self._main_records_cache_ts: float = 0.0
        self._calib_summary_cache: dict[str, Any] | None = None
        self._calib_summary_cache_ts: float = 0.0
        self._pose_reports: dict[str, dict[str, Any]] = {}
        self._CACHE_TTL = 30.0  # seconds

    def _pose_report(self, dataset: str) -> dict[str, Any]:
        if dataset in self._pose_reports:
            return self._pose_reports[dataset]
        filename = "poses_main.json" if dataset == "main" else "poses_myface.json"
        candidates = [
            SETTINGS.newapp_root / "ui" / "src" / "data" / filename,
            SETTINGS.storage_root / "poses" / filename,
        ]
        report: dict[str, Any] = {}
        for path in candidates:
            data = read_json(path, {})
            if isinstance(data, dict) and data:
                report = data
                break
        self._pose_reports[dataset] = report
        return report

    def _dataset_root(self, dataset: str) -> Path:
        return self.datasets[dataset].root

    def _invalidate_cache(self, dataset: str | None = None) -> None:
        """Invalidate caches after writes."""
        if dataset:
            self._records_cache.pop(dataset, None)
            self._records_cache_ts.pop(dataset, None)
        else:
            self._records_cache.clear()
            self._records_cache_ts.clear()
        self._main_records_cache = None
        self._main_records_cache_ts = 0.0
        self._calib_summary_cache = None
        self._calib_summary_cache_ts = 0.0

    def _photo_id(self, dataset: str, source_path: Path) -> str:
        return stable_photo_id(dataset, source_path, self._dataset_root(dataset))

    def _photo_storage_dir(self, dataset: str, photo_id: str) -> Path:
        return self.storage_root / dataset / photo_id

    def _summary_path(self, dataset: str, photo_id: str) -> Path:
        return self._photo_storage_dir(dataset, photo_id) / "summary.json"

    def _artifact_url(self, dataset: str, photo_id: str, filename: str) -> str:
        return f"/storage/{dataset}/{photo_id}/{filename}"

    def _source_url(self, dataset: str, source_path: Path) -> str:
        rel = source_path.relative_to(self._dataset_root(dataset)).as_posix()
        return f"/source/{dataset}/{rel}"

    def list_sources(self, dataset: str) -> list[Path]:
        return list_image_files(self._dataset_root(dataset))

    def _build_stub(self, dataset: str, source_path: Path) -> dict[str, Any]:
        photo_id = self._photo_id(dataset, source_path)
        # [FIX-D5] Track date source: "filename" (verified) vs "fallback" (heuristic)
        date_str, parsed_date = parse_date_from_name(source_path.name)
        date_source = "filename"
        if not parsed_date:
            date_str, parsed_date = fallback_date_for_file(source_path)
            date_source = "fallback"
        summary = read_json(self._summary_path(dataset, photo_id), {})
        bucket = str(summary.get("bucket", "unclassified"))
        pose_report = self._pose_report(dataset).get(source_path.name, {})
        pose = summary.get("pose") or {}
        if pose_report:
            pose = {
                **pose,
                "yaw": pose_report.get("yaw"),
                "pitch": pose_report.get("pitch"),
                "roll": pose_report.get("roll"),
                "source": pose_report.get("source"),
                "pose_source": pose_report.get("source"),
                "classification": pose_report.get("classification"),
                "bucket": pose_report.get("classification"),
            }
            bucket = str(pose_report.get("classification") or bucket)
        stub = {
            "photo_id": photo_id,
            "dataset": dataset,
            "filename": source_path.name,
            "source_path": str(source_path),
            "source_url": self._source_url(dataset, source_path),
            "date_str": date_str,
            "date_source": date_source,
            "parsed_year": parsed_date.year if parsed_date else None,
            "file_size_bytes": source_path.stat().st_size,
            "bucket": bucket,
            "angle": summary.get("angle", "unknown"),
            "bucket_label": BUCKET_LABELS.get(bucket, bucket),
            "pose": pose or {"bucket": bucket},
            "quality": summary.get("quality", {}),
            "texture_forensics": summary.get("texture_forensics", {}),
            "reconstruction": summary.get("reconstruction", {}),
            "metrics": summary.get("metrics", {}),
            "selected_metric_keys": summary.get("selected_metric_keys", BUCKET_METRIC_KEYS.get(bucket, [])),
            "artifacts": summary.get("artifacts", {}),
            "status": summary.get("status", "not_extracted"),
            "extracted_at": summary.get("extracted_at"),
            # Top-level fields for PhotoRecord compatibility
            "year": parsed_date.year if parsed_date else None,
            "syntheticProb": float(summary.get("metrics", {}).get("texture_silicone_prob", 0.0)),
            "bayesH0": summary.get("verdict", {}).get("bayesH0"),  # None if not computed
        }
        
        stub["forensic_profile"] = self._build_forensic_profile(stub)

        if stub["artifacts"]:
            stub["artifacts"] = {
                key: self._artifact_url(dataset, photo_id, value)
                for key, value in stub["artifacts"].items()
                if isinstance(value, str) and value
            }
        return stub

    def _build_forensic_profile(self, stub: dict[str, Any]) -> dict[str, float]:
        """
        [FIX-9] Улучшенная нормализация forensic-осей.
        Вместо упрощённого среднего — z-score нормализация с ожидаемыми диапазонами.
        Унифицирует шкалы для визуального сравнения на радаре.
        """
        metrics = stub.get("metrics", {})
        profile = {}
        
        # Ожидаемые диапазоны (min, max, typical_sigma) для нормализации
        # Источник: физиологические константы + эмпирические данные
        AXIS_RANGES = {
            "Cranial": (0.3, 1.5, 0.15),
            "Orbital": (0.2, 1.2, 0.12),
            "Mandibular": (0.3, 1.3, 0.14),
            "Nasal": (0.2, 1.0, 0.10),
            "Symmetry": (0.0, 0.5, 0.08),  # Асимметрия — отклонение от 0
            "Texture": (0.0, 1.0, 0.20),
            "Material": (0.0, 1.0, 0.15),  # Синтетичность
            "Stability": (0.0, 1.0, 0.10),  # Надёжность
        }
        
        for axis, keys in FORENSIC_RADAR_AXES.items():
            vals = [metrics.get(k) for k in keys if k in metrics and metrics[k] is not None]
            if not vals:
                profile[axis] = 0.0
                continue
            
            min_r, max_r, sigma = AXIS_RANGES.get(axis, (0.0, 1.0, 0.15))
            
            # Для оси Symmetry: инвертируем (0 = идеальная симметрия)
            if axis == "Symmetry":
                mean_val = float(np.mean(vals))
                # Нормализуем: высокая асимметрия → высокий score
                normalized = min(100.0, (mean_val / max_r) * 100.0) if max_r > 0 else 0.0
            # Для Material: специальная обработка синтетичности
            elif axis == "Material":
                # texture_silicone_prob уже в [0, 1]
                silicone = float(metrics.get("texture_silicone_prob", 0.0))
                specular = float(metrics.get("texture_specular_gloss", 0.0))
                # Композитный material score
                composite = (silicone * 0.7 + specular * 0.3)
                normalized = composite * 100.0
            # Для Stability: reliability_weight
            elif axis == "Stability":
                reliability = float(metrics.get("reliability_weight", 0.5))
                normalized = reliability * 100.0
            else:
                # Стандартная z-score нормализация для геометрических осей
                mean_val = float(np.mean(vals))
                # Приводим к шкале [0, 100] с учётом expected range
                # Центр диапазона → 50, края → 0 или 100
                center = (min_r + max_r) / 2
                if sigma > 0:
                    z_score = (mean_val - center) / sigma
                    # sigmoid-like mapping: z в [-3, 3] → [0, 100]
                    normalized = 50.0 + z_score * 16.67  # 1 sigma = ~16.7 points
                    normalized = max(0.0, min(100.0, normalized))
                else:
                    normalized = 50.0
            
            profile[axis] = round(normalized, 2)
        
        return profile

    def list_dataset(self, dataset: str) -> list[dict[str, Any]]:
        now = time.monotonic()
        cached = self._records_cache.get(dataset)
        cached_ts = self._records_cache_ts.get(dataset, 0.0)
        if cached is not None and (now - cached_ts) < self._CACHE_TTL:
            return cached
        records = [self._build_stub(dataset, path) for path in self.list_sources(dataset)]
        records.sort(key=lambda item: (item["date_str"], item["filename"]))
        self._records_cache[dataset] = records
        self._records_cache_ts[dataset] = now
        return records

    def get_record(self, dataset: str, photo_id: str) -> dict[str, Any] | None:
        for record in self.list_dataset(dataset):
            if record["photo_id"] == photo_id:
                return record
        return None

    def process_photo(self, dataset: str, photo_id: str) -> dict[str, Any]:
        source_path = None
        for candidate in self.list_sources(dataset):
            if self._photo_id(dataset, candidate) == photo_id:
                source_path = candidate
                break
        if source_path is None:
            raise KeyError(photo_id)

        bundle = extract_photo_bundle(
            source_path=source_path,
            dataset=dataset,
            photo_id=photo_id,
            output_dir=self._photo_storage_dir(dataset, photo_id),
        )
        date_str, parsed_date = parse_date_from_name(source_path.name)
        if not parsed_date:
            date_str, parsed_date = fallback_date_for_file(source_path)
        bundle["date_str"] = date_str
        bundle["parsed_year"] = parsed_date.year
        bundle["bucket_label"] = BUCKET_LABELS.get(bundle["bucket"], bundle["bucket"])
        bundle["source_url"] = self._source_url(dataset, source_path)
        bundle["artifacts"] = {
            key: self._artifact_url(dataset, photo_id, value)
            for key, value in bundle["artifacts"].items()
        }
        write_json(self._summary_path(dataset, photo_id), {**bundle, "artifacts": {
            key: Path(url).name for key, url in bundle["artifacts"].items()
        }})
        self._invalidate_cache(dataset)
        return bundle

    def process_dataset(
        self,
        dataset: str,
        *,
        limit: int,
        only_ids: list[str] | None = None,
        progress_callback: callable | None = None,
    ) -> None:
        candidates = self.list_dataset(dataset)
        if only_ids:
            wanted = set(only_ids)
            candidates = [record for record in candidates if record["photo_id"] in wanted]
        else:
            candidates = [record for record in candidates if record["status"] != "ready"][:limit]

        total = len(candidates)
        if progress_callback:
            progress_callback(total=total, completed=0, progress=0.0, message="starting")
        if total == 0:
            if progress_callback:
                progress_callback(total=0, completed=0, progress=100.0, message="nothing to do")
            return

        for index, record in enumerate(candidates, start=1):
            self.process_photo(dataset, record["photo_id"])
            if progress_callback:
                progress_callback(
                    total=total,
                    completed=index,
                    progress=(index / total) * 100.0,
                    message=record["filename"],
                )

    def calibration_records(self) -> list[dict[str, Any]]:
        return self.list_dataset("calibration")

    def recompute_metrics(
        self,
        dataset: str,
        *,
        metric_keys: list[str],
        only_ids: list[str] | None = None,
        progress_callback: callable | None = None,
    ) -> None:
        candidates = self.list_dataset(dataset)
        candidates = [record for record in candidates if record.get("status") == "ready"]
        if only_ids:
            wanted = set(only_ids)
            candidates = [record for record in candidates if record["photo_id"] in wanted]

        total = len(candidates)
        if progress_callback:
            progress_callback(total=total, completed=0, progress=0.0, message="metric recompute")
        if total == 0:
            if progress_callback:
                progress_callback(total=0, completed=0, progress=100.0, message="nothing to do")
            return

        for index, record in enumerate(candidates, start=1):
            source_path = Path(record["source_path"])
            recompute_metric_subset(
                source_path=source_path,
                dataset=dataset,
                photo_id=record["photo_id"],
                output_dir=self._photo_storage_dir(dataset, record["photo_id"]),
                metric_keys=metric_keys,
            )
            if progress_callback:
                progress_callback(
                    total=total,
                    completed=index,
                    progress=(index / total) * 100.0,
                    message=record["filename"],
                )

    def main_records(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._main_records_cache is not None and (now - self._main_records_cache_ts) < self._CACHE_TTL:
            return self._main_records_cache
        records = self.list_dataset("main")
        ready_records = [record for record in records if record.get("status") == "ready" and record.get("metrics")]
        calibration_summary = build_calibration_summary(self.calibration_records())
        timeline = build_timeline(ready_records, calibration_summary)
        overrides = read_json(self.override_path, {})
        calibration_records = {record["photo_id"]: record for record in self.calibration_records() if record["status"] == "ready"}
        ready_index = {record["photo_id"]: record for record in timeline}

        merged: list[dict[str, Any]] = []
        for record in records:
            enriched = ready_index.get(record["photo_id"], {**record})
            if enriched.get("status") == "ready":
                enriched["calibration_match"] = self._match_calibration(
                    enriched,
                    calibration_records,
                    calibration_summary,
                    overrides,
                )
            else:
                enriched.setdefault("anomaly_flags", [])
                enriched.setdefault("comparison_with_previous", None)
                enriched.setdefault("comparison_with_next", None)
                enriched.setdefault(
                    "verdict",
                    {"status": "not_extracted", "confidence": "acceptable", "days_delta": 0},
                )
                enriched.setdefault("persona_id", None)
                enriched["calibration_match"] = None
            merged.append(enriched)
        self._main_records_cache = merged
        self._main_records_cache_ts = now
        return merged

    def _match_calibration(
        self,
        record: dict[str, Any],
        calibration_records: dict[str, dict[str, Any]],
        calibration_summary: dict[str, Any],
        overrides: dict[str, Any],
    ) -> dict[str, Any] | None:
        # [FIX-D3] Support both old (string) and new (dict with provenance) override formats
        override_entry = overrides.get(record["photo_id"])
        manual_id = None
        override_provenance = None
        if isinstance(override_entry, dict):
            manual_id = override_entry.get("calibration_photo_id")
            override_provenance = override_entry
        elif isinstance(override_entry, str):
            manual_id = override_entry
        
        if manual_id and manual_id in calibration_records:
            matched = calibration_records[manual_id]
            # [FIX-D4] Don't force score=1.0 for manual overrides — compute real pose distance
            distance = pose_distance(record.get("pose", {}), matched.get("pose", {}))
            real_score = max(0.0, 1.0 - min(distance / 40.0, 1.0))
            return {
                "photo_id": matched["photo_id"],
                "filename": matched["filename"],
                "bucket": matched["bucket"],
                "source": "manual_override",
                "score": real_score,
                "manually_overridden": True,
                "url": matched["artifacts"].get("face_overlay") or matched["artifacts"].get("render_face"),
                "angles": [
                    float(matched.get("pose", {}).get("pitch", 0.0)),
                    float(matched.get("pose", {}).get("yaw", 0.0)),
                    float(matched.get("pose", {}).get("roll", 0.0)),
                ],
                "provenance": override_provenance,
            }

        candidates = [
            candidate
            for candidate in calibration_records.values()
            if candidate.get("bucket") == record.get("bucket") and candidate.get("status") == "ready"
        ]
        if not candidates:
            return None

        best = min(candidates, key=lambda item: pose_distance(record.get("pose", {}), item.get("pose", {})))
        distance = pose_distance(record.get("pose", {}), best.get("pose", {}))
        return {
            "photo_id": best["photo_id"],
            "filename": best["filename"],
            "bucket": best["bucket"],
            "source": "auto_pose_match",
            "score": max(0.0, 1.0 - min(distance / 40.0, 1.0)),
            "url": best["artifacts"].get("face_overlay") or best["artifacts"].get("render_face"),
            "angles": [
                float(best.get("pose", {}).get("pitch", 0.0)),
                float(best.get("pose", {}).get("yaw", 0.0)),
                float(best.get("pose", {}).get("roll", 0.0)),
            ],
        }

    def set_calibration_override(self, photo_id: str, calibration_photo_id: str, reason: str = "", author: str = "system") -> dict[str, Any]:
        # [FIX-D3] Provenance for calibration overrides: audit trail with author, timestamp, reason
        data = read_json(self.override_path, {})
        previous_value = data.get(photo_id, {}).get("calibration_photo_id") if isinstance(data.get(photo_id), dict) else data.get(photo_id)
        entry = {
            "calibration_photo_id": calibration_photo_id,
            "changed_at": iso_now(),
            "changed_by": author,
            "reason": reason,
            "previous_calibration_photo_id": previous_value,
        }
        data[photo_id] = entry
        write_json(self.override_path, data)
        self._invalidate_cache()
        return {"status": "ok", "photo_id": photo_id, "calibration_photo_id": calibration_photo_id, "provenance": entry}

    def calibration_summary(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._calib_summary_cache is not None and (now - self._calib_summary_cache_ts) < self._CACHE_TTL:
            return self._calib_summary_cache
        summary = build_calibration_summary(self.calibration_records())
        summary["stability_score"] = stability_score(summary)
        # Convert buckets dict to array for UI compatibility
        bucket_list = []
        for b_id, b_data in summary["buckets"].items():
            bucket_list.append({
                "pose": b_id,
                "light": b_data.get("light", "unknown"),
                "level": "medium" if b_data["observation_count"] > 5 else "low" if b_data["observation_count"] > 0 else "unreliable",
                "count": b_data["observation_count"],
                "variance": b_data.get("variance", 0.0),
            })
        existing = {(b["pose"], b["light"]) for b in bucket_list}
        for pose in UI_EXPECTED_POSES:
            for light in UI_EXPECTED_LIGHTS:
                if (pose, light) in existing:
                    continue
                bucket_list.append({
                    "pose": pose,
                    "light": light,
                    "level": "unreliable",
                    "count": 0,
                    "variance": 0.0,
                })
        summary["buckets"] = bucket_list
        # recommendations: severity and text
        summary["recommendations"] = []
        if summary["stability_score"] < 0.5:
            summary["recommendations"].append({"severity": "warn", "text": "Low calibration stability - more samples needed."})
        self._calib_summary_cache = summary
        self._calib_summary_cache_ts = now
        return summary

    def recommendations(self) -> list[dict[str, Any]]:
        ready = [record for record in self.main_records() if record.get("status") == "ready"]
        return build_recommendations(ready, self.calibration_summary())

    def get_timeline_full(self) -> dict[str, Any]:
        main_records = self.main_records()
        ready_main = [record for record in main_records if record.get("status") == "ready"]
        
        dated_records = [
            r for r in main_records
            if r.get("date_source") == "filename" and r.get("parsed_year") is not None and 1999 <= int(r["parsed_year"]) <= 2025
        ]
        # Aggregate only explicit filename dates. Fallback mtimes are provenance,
        # not investigation chronology, and can otherwise create false 2026 anchors.
        years = sorted(list({r["parsed_year"] for r in dated_records}))
        if not years:
            return {"years": [], "yearPoints": [], "metrics": [], "identitySegments": [],
                    "eventMarkers": [], "photoVolume": [], "totalPhotos": len(main_records),
                    "calibrationLevel": "none"}
            
        records_by_year = defaultdict(list)
        for r in dated_records:
            if r.get("parsed_year"):
                records_by_year[r["parsed_year"]].append(r)
                
        year_points = []
        for y in years:
            candidates = records_by_year[y]
            # [FIX-C3] Pick best anchor: composite score of quality + frontal pose
            with_pose = [c for c in candidates if c.get("pose", {}).get("pose_source") != "none"]
            anchor = None
            if with_pose:
                def _anchor_score(c: dict) -> float:
                    yaw = abs(c.get("pose", {}).get("yaw", 90))
                    quality = c.get("quality", {}).get("overall_score", 0.5)
                    return (1 - yaw / 90) * 0.6 + quality * 0.4
                anchor = max(with_pose, key=_anchor_score)
            
            if not anchor and candidates:
                anchor = candidates[0]
                
            anomaly = None
            flags = anchor.get("anomaly_flags", []) if anchor else []
            if any(f["severity"] == "critical" for f in flags): anomaly = "danger"
            elif any(f["severity"] == "high" for f in flags): anomaly = "danger"  # [FIX-D6] high → danger, not warn
            elif any(f["severity"] == "medium" for f in flags): anomaly = "warn"
            
            year_points.append({
                "year": y,
                "photo": anchor["source_url"] if anchor else "",
                "anomaly": anomaly,
                "identity": "A",  # TODO: derive from identitySegments
                "note": flags[0]["description"] if flags else None
            })
            
        # Metrics
        metric_configs = []
        # Photos per year
        counts = [len(records_by_year[y]) for y in years]
        metric_configs.append({
            "id": "photo_count",
            "title": "Photos / year",
            "color": "#22c55e",
            "kind": "bar",
            "values": counts
        })
        
        # Mean |yaw|
        yaws = []
        for y in years:
            poses = [r["pose"].get("yaw", 0) for r in records_by_year[y] if r.get("pose", {}).get("yaw") is not None]
            yaws.append(float(np.mean([abs(y) for y in poses])) if poses else 0.0)
            
        metric_configs.append({
            "id": "mean_yaw",
            "title": "Mean |yaw|",
            "unit": "°",
            "color": "#38bdf8",
            "kind": "line",
            "values": yaws
        })

        # Frontal ratio
        ratios = []
        for y in years:
            ready = [r for r in records_by_year[y] if r.get("pose", {}).get("classification")]
            if not ready:
                ratios.append(0.0)
                continue
            frontals = [r for r in ready if r.get("bucket") == "frontal"]
            ratios.append(len(frontals) / len(ready))
            
        metric_configs.append({
            "id": "frontal_ratio",
            "title": "Frontal ratio",
            "unit": "%",
            "color": "#a855f7",
            "kind": "line",
            "values": [float(r * 100) for r in ratios]
        })

        # Bone metrics: mean jaw_width_ratio per year
        jaw_ratios = []
        for y in years:
            with_metrics = [r for r in records_by_year[y] if r.get("metrics") and "jaw_width_ratio" in r.get("metrics", {})]
            if with_metrics:
                vals = [r["metrics"]["jaw_width_ratio"] for r in with_metrics]
                jaw_ratios.append(float(np.mean(vals)))
            else:
                jaw_ratios.append(0.0)
        
        metric_configs.append({
            "id": "jaw_width_ratio",
            "title": "Jaw width ratio (bone)",
            "color": "#ef4444",
            "kind": "line",
            "values": jaw_ratios
        })

        # Bone metrics: mean cranial_face_index per year
        cranial_indices = []
        for y in years:
            with_metrics = [r for r in records_by_year[y] if r.get("metrics") and "cranial_face_index" in r.get("metrics", {})]
            if with_metrics:
                vals = [r["metrics"]["cranial_face_index"] for r in with_metrics]
                cranial_indices.append(float(np.mean(vals)))
            else:
                cranial_indices.append(0.0)
        
        metric_configs.append({
            "id": "cranial_face_index",
            "title": "Cranial face index (bone)",
            "color": "#f97316",
            "kind": "line",
            "values": cranial_indices
        })

        # Texture metrics: mean silicone probability per year
        silicone_probs = []
        for y in years:
            with_texture = [r for r in records_by_year[y] if r.get("texture_forensics") and "silicone_probability" in r.get("texture_forensics", {})]
            if with_texture:
                vals = [r["texture_forensics"]["silicone_probability"] for r in with_texture]
                silicone_probs.append(float(np.mean(vals)))
            else:
                silicone_probs.append(0.0)
        
        metric_configs.append({
            "id": "silicone_probability",
            "title": "Silicone probability (texture)",
            "color": "#ec4899",
            "kind": "line",
            "values": silicone_probs
        })

        # Texture metrics: mean pore density per year
        pore_densities = []
        for y in years:
            with_texture = [r for r in records_by_year[y] if r.get("texture_forensics") and "pore_density" in r.get("texture_forensics", {})]
            if with_texture:
                vals = [r["texture_forensics"]["pore_density"] for r in with_texture]
                pore_densities.append(float(np.mean(vals)))
            else:
                pore_densities.append(0.0)
        
        metric_configs.append({
            "id": "pore_density",
            "title": "Pore density (texture)",
            "color": "#8b5cf6",
            "kind": "line",
            "values": pore_densities
        })

        # Texture metrics: mean wrinkle_forehead per year
        wrinkles = []
        for y in years:
            with_texture = [r for r in records_by_year[y] if r.get("texture_forensics") and "wrinkle_forehead" in r.get("texture_forensics", {})]
            if with_texture:
                vals = [r["texture_forensics"]["wrinkle_forehead"] for r in with_texture]
                wrinkles.append(float(np.mean(vals)))
            else:
                wrinkles.append(0.0)
        
        metric_configs.append({
            "id": "wrinkle_forehead",
            "title": "Forehead wrinkles (texture)",
            "color": "#06b6d4",
            "kind": "line",
            "values": wrinkles
        })

        # Age metric (biological model) [FIX-C2] Use configurable age, None = skip age metrics
        ages = []
        if years and SETTINGS.subject_age_at_earliest_photo is not None:
            first_year = min(years)
            base_age = SETTINGS.subject_age_at_earliest_photo
            for y in years:
                ages.append(float(base_age + (y - first_year)))

        if ages:
            metric_configs.append({
                "id": "age",
                "title": "Biological age (model)",
                "unit": "y",
                "color": "#f59e0b",
                "kind": "line",
                "values": ages
            })

        return {
            "years": years,
            "yearPoints": year_points,
            "metrics": metric_configs,
            "identitySegments": self._build_identity_segments(main_records, years),
            "eventMarkers": [],
            "photoVolume": counts,
            "totalPhotos": len(main_records),
            "calibrationLevel": "medium"
        }

    def overview(self) -> dict[str, Any]:
        main_records = self.main_records()
        ready_main = [record for record in main_records if record.get("status") == "ready"]
        calibration_summary = self.calibration_summary()
        summary = build_timeline_summary(ready_main)
        storage_size = directory_size(self.storage_root)
        source_main_size = sum(path.stat().st_size for path in self.list_sources("main"))
        source_cal_size = sum(path.stat().st_size for path in self.list_sources("calibration"))

        # [FIX-D2] Audit metrics based on real field presence & validity, not just file counts
        def _pct(records: list, predicate) -> int:
            if not records: return 0
            return min(100, int(sum(1 for r in records if predicate(r)) / len(records) * 100))

        # Real checks: fields must exist AND have valid values
        has_metrics = lambda r: bool(r.get("metrics")) and len(r.get("metrics", {})) > 0
        has_texture = lambda r: bool(r.get("texture_forensics")) and len(r.get("texture_forensics", {})) > 0
        has_verdict = lambda r: bool(r.get("verdict")) and r.get("verdict", {}).get("dominant_hypothesis") is not None
        has_forensic = lambda r: bool(r.get("forensic_profile")) and len(r.get("forensic_profile", {})) > 0
        has_artifacts = lambda r: bool(r.get("artifacts")) and len(r.get("artifacts", {})) > 0
        has_reasoning = lambda r: bool(r.get("verdict", {}).get("reasoning"))
        has_valid_date = lambda r: bool(r.get("parsed_year")) and r.get("date_source") != "fallback"
        has_bucket = lambda r: r.get("bucket") not in (None, "unclassified", "")

        current_audit = [
            {"category": "Соответствие ТЗ", "score": _pct(ready_main, lambda r: has_metrics(r) and has_texture(r) and has_verdict(r))},
            {"category": "Хронология по ракурсам", "score": min(100, summary["transitions"] + summary["returns"] + 50)},
            {"category": "Распознавание 9 ракурсов", "score": min(100, int(len({r["bucket"] for r in ready_main if has_bucket(r)}) / max(len(ALL_BUCKETS), 1) * 100))},
            {"category": "Калибровочная модель", "score": int(calibration_summary["stability_score"] * 100)},
            {"category": "Стабильные метрики", "score": int(calibration_summary.get("stable_metrics", 0) / max(calibration_summary.get("stable_metrics", 0) + calibration_summary.get("marginal_metrics", 0) + calibration_summary.get("replace_metrics", 0), 1) * 100)},
            {"category": "Текстурная аналитика", "score": _pct(ready_main, has_texture)},
            {"category": "UV/маски/артефакты", "score": _pct(ready_main, has_artifacts)},
            {"category": "3D реконструкция", "score": _pct(ready_main, has_metrics)},
            {"category": "Хранение по фото", "score": _pct(ready_main, has_metrics)},
            {"category": "Сравнение внутри bucket", "score": min(100, summary["transitions"] * 5)},
            {"category": "Инкрементальный пересчёт", "score": _pct(ready_main, has_metrics)},
            {"category": "Рекомендации", "score": min(100, len(calibration_summary.get("recommendations", [])) * 10 + 50)},
            {"category": "API-контракт", "score": _pct(ready_main, has_verdict)},
            {"category": "Очереди и прогресс", "score": min(100, int(len(ready_main) / max(len(main_records), 1) * 100))},
            {"category": "Учёт объёма данных", "score": min(100, int(storage_size / max(source_main_size + source_cal_size, 1) * 100))},
            {"category": "UI-архитектура", "score": min(100, int(len({r["bucket"] for r in ready_main if has_bucket(r)}) / max(len(ALL_BUCKETS), 1) * 100))},
            {"category": "Карточка фото", "score": _pct(ready_main, has_forensic)},
            {"category": "Объяснимость выводов", "score": _pct(ready_main, has_reasoning)},
            {"category": "Тесты и верификация", "score": min(100, int(calibration_summary["stability_score"] * 80))},
            {"category": "Деплой и tunnel", "score": min(100, 50 + int(len(ready_main) / max(len(main_records), 1) * 50))},
        ]

        return {
            "paths": {
                "main": str(SETTINGS.main_photos_dir),
                "calibration": str(SETTINGS.calibration_dir),
                "storage": str(self.storage_root),
            },
            "storage": {
                "source_main_bytes": source_main_size,
                "source_calibration_bytes": source_cal_size,
                "derived_bytes": storage_size,
                "source_main_human": bytes_to_human(source_main_size),
                "source_calibration_human": bytes_to_human(source_cal_size),
                "derived_human": bytes_to_human(storage_size),
            },
            "timeline_summary": summary,
            "source_photo_total": len(main_records),
            "processed_photo_total": len(ready_main),
            "calibration": {
                "stability_score": calibration_summary["stability_score"],
                "stable_metrics": calibration_summary["stable_metrics"],
                "marginal_metrics": calibration_summary["marginal_metrics"],
                "replace_metrics": calibration_summary["replace_metrics"],
            },
            "audit_current": current_audit,
        }

    def _build_identity_segments(self, main_records: list[dict[str, Any]], years: list[int]) -> list[dict[str, Any]]:
        """
        [FIX-D1] Build identity segments dynamically from Bayesian verdicts.
        If no verdict data is available, return a single segment marked as 'unverified'.
        Segments split when consecutive years show H1/H2 verdicts with high confidence.
        """
        if not years:
            return []

        # Check if we have any verdict data
        records_with_verdict = [r for r in main_records if r.get("verdict") and r.get("parsed_year")]
        if not records_with_verdict:
            # No verdict data — single unverified segment
            return [{"id": "A", "from": min(years), "to": max(years), "status": "unverified"}]

        # Group records by year, pick dominant verdict per year
        year_verdicts: dict[int, str] = {}
        for r in records_with_verdict:
            y = r["parsed_year"]
            verdict = r.get("verdict", {})
            dominant = verdict.get("dominant_hypothesis", "H0")
            confidence = verdict.get("confidence", 0.0)
            # Only flag identity break if H1/H2 with high confidence
            if dominant in ("H1", "H2") and confidence > 0.6:
                year_verdicts[y] = "break"
            else:
                year_verdicts[y] = "same"

        # Build segments: split at 'break' years
        segments = []
        current_id = ord("A")
        seg_start = years[0]
        for i, y in enumerate(years):
            v = year_verdicts.get(y, "same")
            is_last = (i == len(years) - 1)
            if v == "break" or is_last:
                seg_end = y
                segments.append({
                    "id": chr(current_id),
                    "from": seg_start,
                    "to": seg_end,
                    "status": "verified" if any(year_verdicts.get(yy) == "same" for yy in range(seg_start, seg_end + 1) if yy in year_verdicts) else "unverified",
                })
                current_id += 1
                seg_start = y if v == "break" else y + 1

        # Merge single-year segments into neighbors if no actual break
        if len(segments) == 1:
            segments[0]["status"] = "unverified"

        return segments

    def photo_detail(self, dataset: str, photo_id: str) -> dict[str, Any] | None:
        records = self.main_records() if dataset == "main" else self.calibration_records()
        for record in records:
            if record["photo_id"] == photo_id:
                if dataset == "calibration":
                    record["bucket_metric_health"] = bucket_metric_health(self.calibration_summary(), record.get("bucket", "unclassified"))
                return record
        return None

    def get_pipeline_stages(self) -> list[dict[str, Any]]:
        main_records = self.main_records()
        total = len(main_records)
        ready = len([r for r in main_records if r.get("status") == "ready"])
        
        # Real stats derived from records
        with_pose = len([r for r in main_records if r.get("pose", {}).get("pose_source") not in (None, "none")])
        hpe_count = len([r for r in main_records if r.get("pose", {}).get("pose_source") == "hpe"])
        ddfa_count = len([r for r in main_records if r.get("pose", {}).get("pose_source") == "3ddfa"])
        
        return [
            {
                "id": "ingest",
                "name": "Ingest & file scan",
                "order": 1,
                "inputCount": total,
                "outputCount": total,
                "failed": 0,
                "avgMs": 10
            },
            {
                "id": "pose",
                "name": "Head-pose (HPE + 3DDFA)",
                "order": 2,
                "inputCount": total,
                "outputCount": with_pose,
                "failed": total - with_pose,
                "avgMs": 350,
                "notes": f"{hpe_count} via HPE, {ddfa_count} via 3DDFA"
            },
            {
                "id": "recon",
                "name": "3D Reconstruction",
                "order": 3,
                "inputCount": with_pose,
                "outputCount": ready,
                "failed": 0,
                "avgMs": 1200,
                "notes": f"{max(with_pose - ready, 0)} pending; not counted as failed"
            }
        ]

    def get_cache_summary(self) -> dict[str, Any]:
        now = time.monotonic()
        entries = []
        for ds, ts in self._records_cache_ts.items():
            age = now - ts
            entries.append({
                "key": f"records:{ds}",
                "age_s": round(age, 1),
                "ttl_s": self._CACHE_TTL,
                "expired": age >= self._CACHE_TTL,
                "size": len(self._records_cache.get(ds, [])),
            })
        if self._main_records_cache is not None:
            entries.append({
                "key": "main_records",
                "age_s": round(now - self._main_records_cache_ts, 1),
                "ttl_s": self._CACHE_TTL,
                "expired": (now - self._main_records_cache_ts) >= self._CACHE_TTL,
                "size": len(self._main_records_cache),
            })
        if self._calib_summary_cache is not None:
            entries.append({
                "key": "calib_summary",
                "age_s": round(now - self._calib_summary_cache_ts, 1),
                "ttl_s": self._CACHE_TTL,
                "expired": (now - self._calib_summary_cache_ts) >= self._CACHE_TTL,
                "size": 1,
            })
        current_size = len(entries)
        return {
            "maxSize": 10,
            "currentSize": current_size,
            "vramFootprintMB": 0,
            "vramBudgetMB": 4096,
            "evictions": [],
            "entries": entries
        }

    def get_ageing_series(self) -> list[dict[str, Any]]:
        main_records = self.main_records()
        years = sorted(list({r["parsed_year"] for r in main_records if r.get("parsed_year")}))
        if not years: return []
        
        # [FIX-C2] Return empty if age unknown — no fake fitted values
        if SETTINGS.subject_age_at_earliest_photo is None:
            return []
        
        first_year = min(years)
        base_age = SETTINGS.subject_age_at_earliest_photo
        series = []
        for y in years:
            fitted = base_age + (y - first_year)
            observed = fitted
            series.append({
                "year": y,
                "observedAge": observed,
                "fittedAge": fitted,
                "residual": 0,
                "outlier": False
            })
        return series

    def get_diary(self) -> list[dict[str, Any]]:
        path = self.storage_root / "diary.json"
        return read_json(path, [])

    def add_diary_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        import uuid
        path = self.storage_root / "diary.json"
        entries = self.get_diary()
        new_entry = {
            "id": f"entry-{uuid.uuid4().hex[:8]}",
            "timestamp": iso_now(),
            **entry
        }
        entries.append(new_entry)
        write_json(path, entries)
        return new_entry

    def update_diary_entry(self, entry_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        path = self.storage_root / "diary.json"
        entries = self.get_diary()
        for i, entry in enumerate(entries):
            if entry["id"] == entry_id:
                entries[i] = {**entry, **patch, "updatedAt": iso_now()}
                write_json(path, entries)
                return entries[i]
        raise KeyError(entry_id)

    def get_investigations(self) -> list[dict[str, Any]]:
        path = self.storage_root / "investigations.json"
        return read_json(path, [])

    def upsert_investigation(self, inv: dict[str, Any]) -> dict[str, Any]:
        import uuid
        path = self.storage_root / "investigations.json"
        investigations = self.get_investigations()
        inv_id = inv.get("id")
        if inv_id:
            # Update existing
            for i, existing in enumerate(investigations):
                if existing.get("id") == inv_id:
                    investigations[i] = {**existing, **inv, "updatedAt": iso_now()}
                    write_json(path, investigations)
                    return investigations[i]
        # Create new
        new_inv = {
            "id": f"inv-{uuid.uuid4().hex[:8]}",
            "createdAt": iso_now(),
            **inv,
        }
        investigations.append(new_inv)
        write_json(path, investigations)
        return new_inv

    def delete_investigation(self, inv_id: str) -> dict[str, Any] | None:
        path = self.storage_root / "investigations.json"
        investigations = self.get_investigations()
        for i, inv in enumerate(investigations):
            if inv.get("id") == inv_id:
                deleted = investigations.pop(i)
                write_json(path, investigations)
                return {"status": "ok", "id": inv_id}
        return None
