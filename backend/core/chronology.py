from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from typing import Any

from .calibration import allowed_metric_delta, confidence_from_ratio
from .config import SETTINGS
from .utils import ALL_BUCKETS, BUCKET_METRIC_KEYS, median


def _reference_medians(records: list[dict[str, Any]], metric_keys: list[str]) -> dict[str, float]:
    ref_records = [
        record
        for record in records
        if record.get("parsed_year", 0) and int(record["parsed_year"]) <= SETTINGS.reference_year_end
    ]
    if not ref_records:
        ref_records = records[: min(5, len(records))]
    result: dict[str, float] = {}
    for key in metric_keys:
        values = [
            float(record["metrics"][key])
            for record in ref_records
            if key in record.get("metrics", {}) and isinstance(record["metrics"][key], (int, float))
        ]
        if values:
            result[key] = median(values)
    return result


def _days_between(prev_date: str, current_date: str) -> int:
    return abs((date.fromisoformat(current_date) - date.fromisoformat(prev_date)).days)


def _texture_spike(current: dict[str, Any], previous: dict[str, Any]) -> float:
    current_value = float(current.get("metrics", {}).get("texture_silicone_prob", 0.0))
    previous_value = float(previous.get("metrics", {}).get("texture_silicone_prob", 0.0))
    rel_weight = current.get("texture_forensics", {}).get("reliability_weight", 1.0)
    return (current_value - previous_value) * rel_weight


def build_timeline(records: list[dict[str, Any]], calibration_summary: dict[str, Any]) -> list[dict[str, Any]]:
    prepared = deepcopy(records)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in prepared:
        grouped[record.get("bucket", "unclassified")].append(record)

    for bucket, bucket_records in grouped.items():
        bucket_records.sort(key=lambda item: (item.get("date_str", ""), item.get("filename", "")))
        metric_keys = BUCKET_METRIC_KEYS.get(bucket, BUCKET_METRIC_KEYS["unclassified"])
        reference = _reference_medians(bucket_records, metric_keys)
        recent_anomaly = False

        for index, record in enumerate(bucket_records):
            record["timeline_index_in_bucket"] = index
            record["timeline_bucket_size"] = len(bucket_records)
            record["selected_metric_keys"] = metric_keys
            record["anomaly_flags"] = []
            record["comparison_with_previous"] = None
            record["comparison_with_next"] = None
            record["verdict"] = {"status": "stable", "confidence": "acceptable", "days_delta": 0}

            if index == 0:
                continue

            previous = bucket_records[index - 1]
            days_delta = _days_between(previous["date_str"], record["date_str"])
            deltas: dict[str, float] = {}
            exceeded: list[str] = []
            ratio_max = 0.0
            
            # --- Forensic clustering and detailed analysis ---
            metric_clusters = {
                "geometry": ["cranial_face_index", "jaw_width_ratio", "interorbital_ratio", "orbital_asymmetry_index"],
                "projection": ["nose_projection_ratio", "chin_projection_ratio", "orbit_depth_L_ratio", "orbit_depth_R_ratio", "forehead_slope_index"],
                "texture": ["texture_silicone_prob", "texture_pore_density", "texture_spot_density", "texture_wrinkle_forehead", "texture_global_smoothness"]
            }
            
            exceeded_clusters = defaultdict(list)
            for key in metric_keys:
                if key not in record.get("metrics", {}) or key not in previous.get("metrics", {}):
                    continue
                current_value = float(record["metrics"][key])
                previous_value = float(previous["metrics"][key])
                delta = current_value - previous_value
                deltas[key] = round(delta, 6)
                
                # [STAB-02] Весовая фильтрация аномалий
                # Пытаемся найти предварительно вычисленный вес
                rel_weight = record.get("metrics", {}).get("reliability_weight")
                if rel_weight is None:
                    rel_weight = record.get("texture_forensics", {}).get("reliability_weight")
                if rel_weight is None:
                    # Fallback: динамический расчет по позе, если веса нет в метаданных
                    pose = record.get("pose", {})
                    rel_weight = 1.0
                    yaw_abs = abs(pose.get("yaw", 0))
                    pitch_abs = abs(pose.get("pitch", 0))
                    if yaw_abs > 30: rel_weight *= 0.3
                    elif yaw_abs > 20: rel_weight *= 0.5
                    if pitch_abs > 20: rel_weight *= 0.5
                
                allowed = allowed_metric_delta(calibration_summary, bucket, key, days_delta)
                
                # Применяем вес к дельте
                effective_delta = abs(delta) * float(rel_weight)
                
                ratio = effective_delta / allowed if allowed > 1e-8 else 0.0
                
                if ratio >= 1.0:
                    exceeded.append(key)
                    # Привязываем метрику к кластеру для описания
                    for cluster_name, keys in metric_clusters.items():
                        if key in keys:
                            exceeded_clusters[cluster_name].append(key)
                
                ratio_max = max(ratio_max, ratio)

            # Специальная проверка на всплеск силикона/синтетики
            texture_spike = _texture_spike(record, previous)
            if texture_spike >= 0.15 and "texture_silicone_prob" in record.get("metrics", {}):
                exceeded.append("texture_silicone_prob")
                if "texture_silicone_prob" not in exceeded_clusters["texture"]:
                    exceeded_clusters["texture"].append("texture_silicone_prob")
                ratio_max = max(ratio_max, 1.5 + texture_spike * 3.0)

            anomaly = len(set(exceeded)) >= 2 or ratio_max >= 2.1
            confidence = confidence_from_ratio(ratio_max)
            details: list[str] = []

            if days_delta > 30:
                record["anomaly_flags"].append(
                    {
                        "type": "long_gap",
                        "severity": "medium",
                        "description": f"Белая зона: {days_delta} дней без соседнего кадра в том же ракурсе.",
                        "metricKeys": [],
                    }
                )
                details.append(f"обнаружен разрыв {days_delta} дней")

            if anomaly:
                # Генерируем детальное forensic-описание
                reasons = []
                if exceeded_clusters["geometry"]:
                    reasons.append("изменение костной структуры (краниальные индексы)")
                if exceeded_clusters["projection"]:
                    reasons.append("сдвиг 3D-проекции (объемы лица)")
                if exceeded_clusters["texture"]:
                    reasons.append("аномалия микротекстуры (силикон/поры)")
                
                if len(exceeded_clusters) >= 2:
                    details.append(f"Кросс-модальная аномалия: {', '.join(reasons)}")
                else:
                    details.append(f"Значительное отклонение: {', '.join(reasons) or 'комплексный индекс'}")

                severity = "critical" if confidence == "impossible" else "high"
                event_type = "transition"
                
                # [PIPE-02] Логика "Identity Swap" (Кросс-модальная агрегация)
                # Если аномалия и в геометрии, и в текстуре — это критический индикатор смены личности
                forensic_score = 0.0
                if exceeded_clusters["geometry"] or exceeded_clusters["projection"]:
                    forensic_score += 0.5 * (ratio_max / 2.1)
                if exceeded_clusters["texture"]:
                    forensic_score += 0.5 * (texture_spike / 0.15 if texture_spike > 0 else 0.5)
                
                if (confidence == "impossible" or forensic_score >= 1.0) and days_delta < 30:
                    event_type = "impossible_short"
                    details[0] = f"Identity Swap Indicator (score {forensic_score:.2f}): {details[0]}"
                    severity = "critical"
                
                record["anomaly_flags"].append(
                    {
                        "type": event_type,
                        "severity": severity,
                        "description": "; ".join(details),
                        "metricKeys": sorted(set(exceeded)),
                        "forensic_score": round(forensic_score, 2),
                    }
                )

            reference_hits = 0
            if reference and index >= 2:
                for key in metric_keys:
                    if key not in reference or key not in record.get("metrics", {}):
                        continue
                    allowed = allowed_metric_delta(calibration_summary, bucket, key, max(days_delta, 30))
                    if abs(float(record["metrics"][key]) - reference[key]) <= allowed * 0.85:
                        reference_hits += 1
                if recent_anomaly and reference_hits >= 2:
                    record["anomaly_flags"].append(
                        {
                            "type": "return",
                            "severity": "high",
                            "description": "метрики вернулись к раннему опорному диапазону этого ракурса",
                            "metricKeys": metric_keys[:3],
                        }
                    )

            recent_anomaly = any(flag["type"] in {"transition", "impossible_short"} for flag in record["anomaly_flags"])

            record["comparison_with_previous"] = {
                "previousPhotoId": previous.get("photo_id", ""),
                "previousDate": previous.get("date_str", ""),
                "previousFilename": previous.get("filename", ""),
                "daysBetween": days_delta,
                "metricDeltas": deltas,
                "anomalyDetected": anomaly,
                "anomalyDetails": details or ["стабильное изменение"],
                "confidenceLevel": confidence,
                "poseBucket": bucket,
                "comparisonScope": "same_pose_timeline",
            }

            if record["anomaly_flags"]:
                dominant = record["anomaly_flags"][0]
                verdict_status = dominant["type"]
                if dominant["type"] == "long_gap":
                    verdict_status = "gap"
                record["verdict"] = {
                    "status": verdict_status,
                    "confidence": confidence,
                    "days_delta": days_delta,
                }
            else:
                record["verdict"] = {
                    "status": "stable",
                    "confidence": confidence,
                    "days_delta": days_delta,
                }

        for index, record in enumerate(bucket_records[:-1]):
            next_record = bucket_records[index + 1]
            if not next_record.get("comparison_with_previous"):
                continue
            record["comparison_with_next"] = {
                "nextPhotoId": next_record["photo_id"],
                "nextDate": next_record["date_str"],
                "nextFilename": next_record["filename"],
                "daysBetween": next_record["comparison_with_previous"]["daysBetween"],
                "anomalyDetected": next_record["comparison_with_previous"]["anomalyDetected"],
                "anomalyDetails": next_record["comparison_with_previous"]["anomalyDetails"],
                "confidenceLevel": next_record["comparison_with_previous"]["confidenceLevel"],
                "poseBucket": bucket,
                "comparisonScope": "same_pose_timeline",
            }

    flattened = [record for bucket in grouped.values() for record in bucket]
    flattened.sort(key=lambda item: (item.get("date_str", ""), item.get("filename", "")))

    from .persona import cluster_personas
    persona_groups = cluster_personas(flattened)
    persona_map = {}
    for group in persona_groups:
        for pid in group["photo_ids"]:
            persona_map[pid] = group["persona_id"]
    
    for record in flattened:
        record["persona_id"] = persona_map.get(record["photo_id"])

    return flattened


def build_timeline_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = {bucket: 0 for bucket in ALL_BUCKETS}
    transitions = 0
    returns = 0
    impossible = 0
    gaps = 0
    critical_events: list[dict[str, Any]] = []

    for record in records:
        bucket = record.get("bucket")
        if bucket in coverage:
            coverage[bucket] += 1
        for flag in record.get("anomaly_flags", []):
            if flag["type"] == "return":
                returns += 1
            elif flag["type"] == "long_gap":
                gaps += 1
            elif flag["type"] == "impossible_short":
                impossible += 1
                critical_events.append(
                    {
                        "date": record.get("date_str"),
                        "filename": record.get("filename"),
                        "angle": bucket,
                        "description": flag.get("description", ""),
                    }
                )
            elif flag["type"] == "transition":
                transitions += 1
                if flag.get("severity") == "critical":
                    critical_events.append(
                        {
                            "date": record.get("date_str"),
                            "filename": record.get("filename"),
                            "angle": bucket,
                            "description": flag.get("description", ""),
                        }
                    )

    persona_ids = {r["persona_id"] for r in records if r.get("persona_id")}
    
    return {
        "total_photos": len(records),
        "transitions": transitions,
        "returns": returns,
        "impossible_changes": impossible,
        "long_gaps": gaps,
        "persona_count": len(persona_ids),
        "angle_coverage": coverage,
        "critical_events": critical_events[:30],
    }
