from __future__ import annotations

from collections import defaultdict
from math import sqrt
from typing import Any

from .config import SETTINGS
from .utils import ALL_BUCKETS, BUCKET_METRIC_KEYS, clamp, mad, median


def pose_distance(pose_a: dict[str, Any], pose_b: dict[str, Any]) -> float:
    yaw = float(pose_a.get("yaw", 0.0)) - float(pose_b.get("yaw", 0.0))
    pitch = float(pose_a.get("pitch", 0.0)) - float(pose_b.get("pitch", 0.0))
    roll = float(pose_a.get("roll", 0.0)) - float(pose_b.get("roll", 0.0))
    return sqrt(yaw * yaw + pitch * pitch + roll * roll)


def _metric_status(robust_cv: float, spread: float, observation_count: int) -> str:
    if observation_count < 3:
        return "marginal"
    if robust_cv <= 0.12 or spread <= 0.015:
        return "stable"
    if robust_cv <= 0.24 or spread <= 0.03:
        return "marginal"
    return "replace"


def build_calibration_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    extracted = [record for record in records if record.get("status") == "ready" and record.get("metrics")]
    buckets: dict[str, Any] = {}
    flat_metrics: list[dict[str, Any]] = []

    for bucket in ALL_BUCKETS + ["unclassified"]:
        bucket_records = [record for record in extracted if record.get("bucket") == bucket]
        metric_map: dict[str, Any] = {}
        best_reference = None
        best_reference_score = float("inf")

        for record in bucket_records:
            pose_score = abs(float(record.get("pose", {}).get("yaw", 0.0))) + abs(float(record.get("pose", {}).get("pitch", 0.0)))
            quality_penalty = 0.0 if not record.get("quality", {}).get("flags", {}).get("QUALITY_REJECTED_TEXTURE") else 20.0
            score = pose_score + quality_penalty
            if score < best_reference_score:
                best_reference_score = score
                best_reference = record

        values_by_metric: dict[str, list[float]] = defaultdict(list)
        for record in bucket_records:
            for key, value in (record.get("metrics") or {}).items():
                if isinstance(value, (int, float)):
                    values_by_metric[key].append(float(value))

        for key, values in values_by_metric.items():
            if not values:
                continue
            med = median(values)
            spread = mad(values)
            robust_cv = spread / abs(med) if abs(med) > 1e-6 else spread
            status = _metric_status(robust_cv, spread, len(values))
            info = {
                "key": key,
                "median": med,
                "mad": spread,
                "robust_cv": robust_cv,
                "status": status,
                "observation_count": len(values),
            }
            metric_map[key] = info
            flat_metrics.append({**info, "bucket": bucket})

        buckets[bucket] = {
            "bucket": bucket,
            "observation_count": len(bucket_records),
            "reference_photo_id": best_reference.get("photo_id") if best_reference else None,
            "metrics": metric_map,
        }

    stable_count = sum(1 for item in flat_metrics if item["status"] == "stable")
    marginal_count = sum(1 for item in flat_metrics if item["status"] == "marginal")
    replace_count = sum(1 for item in flat_metrics if item["status"] == "replace")

    return {
        "calibration_type": "pose_noise_model_v2",
        "observation_count": len(extracted),
        "bucket_coverage": {bucket: buckets[bucket]["observation_count"] for bucket in buckets},
        "stable_metrics": stable_count,
        "marginal_metrics": marginal_count,
        "replace_metrics": replace_count,
        "metrics": flat_metrics,
        "buckets": buckets,
    }


def allowed_metric_delta(
    calibration_summary: dict[str, Any],
    bucket: str,
    metric_key: str,
    days_delta: int,
) -> float:
    bucket_info = calibration_summary.get("buckets", {}).get(bucket, {})
    metric_info = bucket_info.get("metrics", {}).get(metric_key, {})
    spread = float(metric_info.get("mad", 0.0))
    status = metric_info.get("status", "marginal")
    base = max(spread * 3.0, 0.012)
    if metric_key.startswith("texture_"):
        base = max(spread * 3.0, 0.04)
    if status == "replace":
        base *= 1.4
    elif status == "stable":
        base *= 0.9

    if days_delta < 14:
        return base * 0.75
    if days_delta < 30:
        return base * 0.85
    if days_delta > 3650:
        return base * 1.5
    if days_delta > 365:
        return base * 1.2
    return base


def bucket_metric_health(calibration_summary: dict[str, Any], bucket: str) -> list[dict[str, Any]]:
    metrics = calibration_summary.get("buckets", {}).get(bucket, {}).get("metrics", {})
    ordered: list[dict[str, Any]] = []
    for key in BUCKET_METRIC_KEYS.get(bucket, []):
        if key in metrics:
            ordered.append(metrics[key])
    for key, value in metrics.items():
        if key not in {item["key"] for item in ordered}:
            ordered.append(value)
    return ordered


def confidence_from_ratio(ratio: float) -> str:
    if ratio >= 2.8:
        return "impossible"
    if ratio >= 1.6:
        return "unlikely"
    return "acceptable"


def stability_score(calibration_summary: dict[str, Any]) -> float:
    metrics = calibration_summary.get("metrics", [])
    if not metrics:
        return 0.0
    scores = []
    for metric in metrics:
        status = metric.get("status")
        observation_count = int(metric.get("observation_count", 0))
        if status == "stable":
            score = 1.0
        elif status == "marginal":
            score = 0.55
        else:
            score = 0.1
        if observation_count < 3:
            score *= 0.55
        scores.append(score)
    return clamp(sum(scores) / len(scores), 0.0, 1.0)
